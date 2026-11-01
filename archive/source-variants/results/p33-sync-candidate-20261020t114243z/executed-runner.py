"""Offline comparison of source-registered sync_id candidate; never edits projects or boards."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
from p30_run import ROOT, BIN, run_logged

BASELINE = ROOT / 'results/p33-abort-reset-20261020T113240Z/report.json'
EXPECTED_BENCH = '06ad3599e30ff347890482961e3f2d347a619a3a2f1f55986c31603e9cd6cd56'
EXPECTED_ARB = '9d61f5cef904d43f921999790a7b70ecf0ebf61df51c699d8a755ac190653c74'
MONITOR = r"""
  // Identical additional invariants in baseline and candidate cases.
  reg p33_prior_valid=0, p33_prior_do_enable=0;
  reg [2:0] p33_prior_request_id=0;
  integer p33_gate_checks=0,p33_frozen_tail_checks=0;
  always @(posedge qclk)begin
    if(!rst)begin
      p33_prior_valid=0;
      p33_prior_do_enable=0;
      p33_prior_request_id=0;
    end else begin
      p33_gate_checks=p33_gate_checks+1;
      if(dut.do_enable && (dut.sync_id || dut.sync_id_ret_src || dut.sync_id_ret_dest))
        $fatal(1,"P33_GATE_INVARIANT TX=%0d sync=%b src_ack=%b dest_ack=%b",
          TX,dut.sync_id,dut.sync_id_ret_src,dut.sync_id_ret_dest);
      // Evaluate pre-NBA values: current ID reflects the previous active edge.
      if(p33_prior_valid && !p33_prior_do_enable)begin
        p33_frozen_tail_checks=p33_frozen_tail_checks+1;
        if(dut.request_id !== p33_prior_request_id)
          $fatal(1,"P33_TAIL_MOVED_WHILE_DISABLED TX=%0d old=%h new=%h",
            TX,p33_prior_request_id,dut.request_id);
      end
      p33_prior_valid=1;
      p33_prior_do_enable=dut.do_enable;
      p33_prior_request_id=dut.request_id;
    end
  end
  always @(posedge done)begin
    $display("P33_LOCAL_INVARIANTS_PASS TX=%0d gate_checks=%0d frozen_tail_checks=%0d",TX,p33_gate_checks,p33_frozen_tail_checks);
  end
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('replacement anchor count differs: ' + repr(old[:90]))
    return text.replace(old, new)


def candidate_arb(text):
    text = replace_once(text, 'wire sync_id;', "reg sync_id = 1'b0;")
    text = replace_once(text,
        'assign sync_id = ~enabled_dest && ~enabled_src && request_id != response_id;',
        """// P33 offline candidate: register the source-domain comparison before CDC.
always @(posedge req_aclk) begin
  if (req_aresetn == 1'b0)
    sync_id <= 1'b0;
  else
    sync_id <= ~enabled_dest && ~enabled_src && request_id != response_id;
end""")
    text = replace_once(text,
        'if (~sync_id_ret_dest && ~sync_id_ret_src &&',
        'if (~sync_id && ~sync_id_ret_dest && ~sync_id_ret_src &&')
    return text


def instrument(bench, half_period):
    bench = replace_once(bench, '#16.3;', '#' + half_period + ';')
    # Controlled comparison only: exclude the earliest FIFO producer start
    # whose overflow is retained as an unresolved finding in the prior runs.
    # This follows actual XFER_REQ edges, rather than a global startup delay;
    # it is NOT a repaired interface contract or a production workaround.
    guard = """
  integer p33_wr_high_edges=0;
  always @(posedge fclk)begin
    if(!rst || !enable || !wr_request)p33_wr_high_edges<=0;
    else if(p33_wr_high_edges<3)p33_wr_high_edges<=p33_wr_high_edges+1;
  end
"""
    bench = replace_once(bench,
        'enable && wr_request && sent<target',
        'enable && wr_request && p33_wr_high_edges>=3 && sent<target')
    bench = replace_once(bench, '  integer before_sync,k;reg observed;',
        guard + '\n  integer before_sync,k;reg observed;')
    return replace_once(bench, '  integer before_sync,k;reg observed;', MONITOR + '\n  integer before_sync,k;reg observed;')


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p33-sync-candidate-' + stamp)
    out.mkdir(exist_ok=False)
    work = Path('E:/p33-sync-candidate-' + stamp)
    work.mkdir(exist_ok=False)
    report = dict(
        status='running', work=str(work), baseline_report=str(BASELINE),
        baseline_report_sha256=digest(BASELINE.read_bytes()), sources=[],
        comparisons=[], board_operations=False, project_modified=False,
        vendor_sources_modified=False, CDC_waivers_added=False,
        candidate_scope='Source req_aclk register for sync_id plus explicit !sync_id in re-enable gate only; no enabled/empty status register. Four digital runs with identical instrumentation per clock ratio. No physical CDC/routed/hardware closure.',
        invariant_sampling='qclk active-edge pre-NBA: no do_enable with sync request or returned ack, and request tail unchanged when prior do_enable was zero.',
        reset_scope='Existing fixture coordinates all AXI/DUT resets and pauses sample clock through release; arbitrary one-sided live AXI reset remains outside scope.')
    report['producer_scope']='External RX starts only after three consecutive sample-clock active edges of XFER_REQ, and keeps the existing 1-in-4 strobe rate. This narrowly excludes the unresolved earliest-start overflow; it is not proof that immediate XFER_REQ-based operation is safe. No overflow assertion is removed.'
    report['prior_unresolved_comparisons']=[str(ROOT/'results/p33-sync-candidate-20261020T113545Z/report.json'),str(ROOT/'results/p33-sync-candidate-20261020T113745Z/report.json')]
    source_bytes = {}
    original_paths = {}
    snapshot = out / 'inputs'
    snapshot.mkdir()
    runner_bytes=Path(__file__).read_bytes()
    (out/'executed-runner.py').write_bytes(runner_bytes)
    report['runner_sha256']=digest(runner_bytes)
    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    try:
        baseline = json.loads(BASELINE.read_text('utf-8'))
        if baseline['status'] != 'passed':
            raise RuntimeError('pinned baseline report is not passed')
        for item in baseline['sources']:
            path = Path(item['path'])
            data = path.read_bytes()
            if digest(data) != item['sha256']:
                raise RuntimeError('pinned source changed: ' + str(path))
            if path.name in source_bytes:
                raise RuntimeError('duplicate input basename')
            source_bytes[path.name] = data
            original_paths[path.name] = path
            (snapshot/path.name).write_bytes(data)
            report['sources'].append(dict(path=str(path), name=path.name, sha256=digest(data)))
        arb = source_bytes['request_arb.v']
        bench_name = 'tb_p33_dma_abort.sv'
        bench = source_bytes[bench_name]
        if digest(arb) != EXPECTED_ARB or digest(bench) != EXPECTED_BENCH:
            raise RuntimeError('explicit arb/bench pin mismatch')
        arb_text = arb.decode('utf-8')
        candidate = candidate_arb(arb_text).encode('utf-8')
        (out/'request_arb.candidate.v').write_bytes(candidate)
        (out/'request_arb.patch').write_text(''.join(difflib.unified_diff(
            arb_text.splitlines(keepends=True), candidate.decode().splitlines(keepends=True),
            fromfile='baseline/request_arb.v', tofile='candidate/request_arb.v')), encoding='utf-8')
        report['candidate_sha256'] = digest(candidate)
        report['bench_instrumentation_sha256'] = digest(MONITOR.encode())
        save()
        # The original short-descriptor consumer fixture is rate limited. A
        # prior 3.7ns trial underflowed identically in BOTH versions before the
        # abort scenario; its failed evidence is retained separately. These
        # two accepted finite cases do not claim faster-sample support.
        for ratio, half_period in [('slow_sample', '16.3'), ('slower_sample', '27.1')]:
            ratio_bench = instrument(bench.decode('utf-8'), half_period).encode('utf-8')
            ratio_report = dict(name=ratio, req_half_period_ns=5.0,
                sample_half_period_ns=float(half_period), bench_sha256=digest(ratio_bench), runs=[])
            report['comparisons'].append(ratio_report)
            save()
            for variant, rtl_bytes in [('baseline', arb), ('candidate', candidate)]:
                label = ratio + '-' + variant
                subwork = work/label
                subwork.mkdir()
                subout = out/label
                subout.mkdir()
                for name, data in source_bytes.items():
                    actual = rtl_bytes if name == 'request_arb.v' else ratio_bench if name == bench_name else data
                    (subwork/name).write_bytes(actual)
                (subout/bench_name).write_bytes(ratio_bench)
                (subout/'request_arb.v').write_bytes(rtl_bytes)
                run = dict(variant=variant, status='running', work=str(subwork),
                    rtl_sha256=digest(rtl_bytes), bench_sha256=digest(ratio_bench), commands=[])
                ratio_report['runs'].append(run)
                save()
                snapshot_name = 'p33_sync_' + ratio + '_' + variant
                commands = [
                    ('compile-rtl', [str(BIN/'xvlog.bat'), '--relax',
                        *[n for n in source_bytes if n.endswith('.v')]]),
                    ('compile-bench', [str(BIN/'xvlog.bat'), '--sv', bench_name]),
                    ('elaborate', [str(BIN/'xelab.bat'), '-mt', '2', '-timescale',
                        '1ns/1ps', 'tb_p33_dma_abort', '-s', snapshot_name]),
                    ('simulate', [str(BIN/'xsim.bat'), snapshot_name, '-runall'])]
                for command_name, command in commands:
                    log = subout/(command_name+'.txt')
                    code = run_logged(command, subwork, log, 180)
                    text = log.read_text('utf-8', errors='replace')
                    run['commands'].append(dict(name=command_name, exit_code=code))
                    save()
                    if code or 'ERROR:' in text or 'Fatal:' in text:
                        run.update(status='failed', failed_command=command_name)
                        break
                else:
                    markers = [line for line in text.splitlines() if line.startswith('P33_')]
                    run['markers'] = markers
                    if ('P33_ABORT_RESET_TB_PASS cases=2' not in markers or
                        sum(line.startswith('P33_LOCAL_INVARIANTS_PASS') for line in markers) != 2):
                        run.update(status='failed', error='required completion/invariant markers missing')
                    else:
                        run['status'] = 'passed'
                save()
        report['status'] = 'passed' if all(run['status']=='passed'
            for comp in report['comparisons'] for run in comp['runs']) else 'failed'
    except Exception as exc:
        report.update(status='failed', error=repr(exc))
    finally:
        report['original_source_hashes_unchanged'] = all(
            path.exists() and path.read_bytes() == source_bytes[name]
            for name,path in original_paths.items())
        if not report['original_source_hashes_unchanged']:
            report['status']='failed'
            report['source_changed_during_run']=True
        save()
        print(out)
        print(report['status'])
        print(report.get('error',''))
    return 0 if report['status']=='passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

