"""Replay the unequal slow-ratio results with local producer diagnostics, no board/project writes."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from p30_run import ROOT,BIN,run_logged
from p33_sync_candidate import MONITOR,candidate_arb,replace_once
PINNED=ROOT/'results/p33-sync-candidate-20261020T113745Z'
TRACE=r"""
  integer p33_trace_count=0;
  always @(posedge fclk)begin
    if(rst && !TX && wr_en &&
      ((epoch==3 && sent<5) || !dut.src_ready || !dut.src_enable || !dut.src_enabled))begin
      if(p33_trace_count<30)begin
        $display("P33_RX_EDGE t=%0t epoch=%0d sent=%0d rec=%0d en=%b wr_en=%b wr_req=%b src_enable=%b src_enabled=%b src_valid=%b src_ready=%b req_v=%b req_r=%b tail=%h src_tail=%h src_resp=%h qresp=%h sync=%b src_sync=%b dbg=%h",
          $time,epoch,sent,received,enable,wr_en,wr_request,dut.src_enable,dut.src_enabled,
          dut.src_valid,dut.src_ready,dut.src_req_valid,dut.src_req_ready,
          dut.request_id,dut.src_request_id,dut.src_response_id,dut.response_id,dut.sync_id,dut.src_sync_id,dut.dbg_status);
        p33_trace_count=p33_trace_count+1;
      end
    end
  end
"""
def sha(b):return hashlib.sha256(b).hexdigest()
def instrument(bench, half_period):
  # Keep this reproducer on the original earliest-start stimulus even when
  # the separate controlled-comparison runner adds a producer start policy.
  bench=replace_once(bench,'#16.3;','#'+half_period+';')
  return replace_once(bench,'  integer before_sync,k;reg observed;',MONITOR+'\n  integer before_sync,k;reg observed;')
def main():
  stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
  out=ROOT/'results'/('p33-sync-trace-'+stamp);out.mkdir(exist_ok=False)
  work=Path('E:/p33-sync-trace-'+stamp);work.mkdir(exist_ok=False)
  pinned=json.loads((PINNED/'report.json').read_text('utf-8'))
  sources={i['name']:(PINNED/'inputs'/i['name']).read_bytes() for i in pinned['sources']}
  for i in pinned['sources']:
    if sha(sources[i['name']])!=i['sha256']:raise RuntimeError('snapshot mismatch '+i['name'])
  report=dict(status='running',source_comparison=str(PINNED),runs=[],board_operations=False,
      project_modified=False,vendor_modified=False,scope='27.1ns sample-half-period replay with same local source-edge diagnostics in both versions; pre-NBA prints are contextual diagnostics, not new CDC proof.')
  def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
  bench=instrument(sources['tb_p33_dma_abort.sv'].decode(),'27.1')
  bench=replace_once(bench,'  integer before_sync,k;reg observed;',TRACE+'\n  integer before_sync,k;reg observed;')
  bench=replace_once(bench,'$fatal(1,"normal RX producer overflow");',
      '$fatal(1,"normal RX producer overflow epoch=%0d sent=%0d rec=%0d do_enable=%b src_enable=%b src_enabled=%b src_ready=%b tail=%h src_tail=%h src_resp=%h",epoch,sent,received,dut.do_enable,dut.src_enable,dut.src_enabled,dut.src_ready,dut.request_id,dut.src_request_id,dut.src_response_id);')
  try:
    for variant in ['baseline','candidate']:
      d=work/variant;d.mkdir()
      od=out/variant;od.mkdir()
      arb=sources['request_arb.v'] if variant=='baseline' else candidate_arb(sources['request_arb.v'].decode()).encode()
      for name,raw in sources.items():
        data=arb if name=='request_arb.v' else bench.encode() if name.endswith('.sv') else raw
        (d/name).write_bytes(data)
      (od/'tb_p33_dma_abort.sv').write_text(bench,encoding='utf-8')
      r=dict(variant=variant,status='running',commands=[],rtl_sha256=sha(arb),bench_sha256=sha(bench.encode()))
      report['runs'].append(r);save()
      for label,cmd in [
        ('compile-rtl',[str(BIN/'xvlog.bat'),'--relax',*[n for n in sources if n.endswith('.v')]]),
        ('compile-bench',[str(BIN/'xvlog.bat'),'--sv','tb_p33_dma_abort.sv']),
        ('elaborate',[str(BIN/'xelab.bat'),'-mt','2','-timescale','1ns/1ps','tb_p33_dma_abort','-s','p33_trace']),
        ('simulate',[str(BIN/'xsim.bat'),'p33_trace','-runall'])]:
        code=run_logged(cmd,d,od/(label+'.txt'),180)
        text=(od/(label+'.txt')).read_text('utf-8',errors='replace')
        r['commands'].append(dict(name=label,exit_code=code));save()
        if code or 'ERROR:' in text or 'Fatal:' in text:
          r.update(status='failed',failed_command=label)
          break
      else:r['status']='passed' if 'P33_ABORT_RESET_TB_PASS cases=2' in text else 'incomplete'
      r['diagnostics']=[line for line in text.splitlines() if line.startswith('P33_') or line.startswith('Fatal:')]
      save()
    report['status']='diagnostic_replay_completed'
  except Exception as exc:report.update(status='failed',error=repr(exc))
  finally:save();print(out);print(report['status'])
if __name__=='__main__':main()

