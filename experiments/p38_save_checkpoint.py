"""Verify complete saved periodic buffers and write a local restart checkpoint.

No serial, board, RF, software launch or shutdown operation is performed here.
ZIP preserves sources, selected raw evidence and the external routed design.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from p32_session import ROOT
from p37_review_archives import archive_bytes


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def verify_cycles(trial_path, archive_path):
    trial = json.loads(trial_path.read_text('utf-8'))
    archive, raw = archive_bytes(archive_path)
    if (trial['status'] != 'passed_periodic_RX_and_LCD_draw_with_independent_idle_readback'
            or not trial['independent_final_idle_verified']
            or archive['expected_boot'] != trial['expected_boot']
            or len(raw) != trial['requested_cycles']*262144):
        raise ValueError('trial/archive contract mismatch')
    rows = []
    for i, cycle in enumerate(trial['cycles']):
        block = raw[i*262144:(i+1)*262144]
        digest = sha(block)
        if cycle['cycle'] != i or digest != cycle['raw_sha256']:
            raise ValueError('original cycle bytes differ at '+str(i))
        rows.append(dict(cycle=i, byte_offset=i*262144, bytes=262144, sha256=digest))
    if len(rows) != trial['requested_cycles']: raise ValueError('cycle list incomplete')
    return dict(trial=str(trial_path.resolve()), trial_sha256=sha(trial_path.read_bytes()),
                archive_report=str(archive_path.resolve()),
                concatenated_raw_file=str((archive_path.parent/archive['local_raw_file']).resolve()),
                raw_bytes=len(raw), raw_sha256=sha(raw), cycles=rows,
                all_original_returned_cycle_bytes_verified=True,
                hardware_continuity_proven=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full-archive', required=True, type=Path)
    p.add_argument('--short-archive', required=True, type=Path)
    p.add_argument('--preflight-report', required=True, type=Path)
    args = p.parse_args()
    full = verify_cycles(ROOT/'results/p38-board-20261021T094451Z/report.json', args.full_archive)
    short = verify_cycles(ROOT/'results/p38-board-20261021T094240Z/report.json', args.short_archive)
    preflight = json.loads(args.preflight_report.read_text('utf-8'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'results'/('p38-stop-'+stamp); out.mkdir(exist_ok=False)
    write_json(out/'cycles-64.json', full); write_json(out/'cycles-8.json', short)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    now = datetime.now(timezone.utc).isoformat()
    state_path = ROOT/'TX-SOURCE-STATUS.json'
    state = json.loads(state_path.read_text('utf-8'))
    if state['authoritative_current_field'] != 'p38_current':
        raise RuntimeError('newer checkpoint exists; do not overwrite')
    current = state['p38_current']
    latest_board = preflight.get('boards', {}).get('COM8', {})
    stopped_state_confirmed = (preflight.get('status')=='both_boards_identified'
        and preflight.get('serial_closed') is True
        and latest_board.get('boot_id')==current['last_identified_boot']
        and latest_board.get('tainted')=='0' and latest_board.get('guard_matches') is True
        and latest_board.get('rf_ready') is True and latest_board.get('buffer_enable')=='0'
        and latest_board.get('scan_enable')==['0']*4
        and latest_board.get('experiment_process_observed') is False
        and preflight['boards']['COM9'].get('experiment_process_observed') is False)
    current.update(save_checkpoint_utc=now, all_cycle_raw_IQ_on_host=True,
                   other_63_raw_cycles_RAM_only=False, short_trial_all_raw_IQ_on_host=True,
                   all_64_cycle_raw_archive=(args.full_archive.relative_to(ROOT) if args.full_archive.is_absolute() else args.full_archive).as_posix(),
                   all_8_cycle_raw_archive=(args.short_archive.relative_to(ROOT) if args.short_archive.is_absolute() else args.short_archive).as_posix(),
                   all_64_cycle_byte_manifest=str((out/'cycles-64.json').relative_to(ROOT)),
                   all_8_cycle_byte_manifest=str((out/'cycles-8.json').relative_to(ROOT)),
                   stop_checkpoint=str((out/'report.json').relative_to(ROOT)),
                   stop_record='docs/handoff/STOP-P38-20261021.md',
                   latest_stop_preflight=args.preflight_report.resolve().relative_to(ROOT).as_posix(),
                   board_stop_state_readback_confirmed=stopped_state_confirmed,
                   poweroff_issued_by_this_save=False)
    write_json(state_path, state)
    stop = '''# P38停工保存与下次接线恢复

保存日期：2026-10-21。功能进度仍为P38；本次只保存资料，没有新增功能验收或关机/重启操作。

## 已保存在电脑

- START-HERE、TX-SOURCE-STATUS.json、P37/P38实验记录和恢复清单。
- 已验证的安全时钟原生固件、配对overlay、板端周期接收/频谱程序及源码、测试和构建报告。
- P37完整4MiB返回数据；P38的64轮和8轮原始返回数据现均完整归档。逐轮SHA与原始板端实验报告逐一相符，可按manifest里的offset/bytes从串接文件恢复各轮原始文件。相互独立的轮次仍不证明连续无丢样。
- P38最后画面回读图和独立NumPy数值核对。

最新归档、逐轮清单及ZIP位置见TX-SOURCE-STATUS.json的p38_current和其stop_checkpoint。

## 下次接线、通电后

1. 保持原接线和拨码，先不手动启动发射、不占用COM8/COM9，不热拔屏幕排线。
2. AI先读START-HERE及[当前恢复清单](RESUME-P38-20261021.md)，重新读取板卡身份、实际boot_id、内核状态及RF/显示设备；不能复用上次boot参数。
3. 普通重新上电会进入原厂家RF模式，未设置合并显示开机自启。按[P37清单](RESUME-P37-20261021.md)核对文件，受控新hold启动、单次加载安全位流及匹配overlay，重新建立同boot时钟验收。禁止在驱动已绑定时热卸载/重配PL。
4. 验收RF/显示后，从P38周期监测继续。已有源码/固件/原始证据都可复用，不必重新开发；仍需执行本次启动的硬件状态验证。
5. 下一任务是重复启动/0xFF定位、延长有界监测及恢复测试，再做持续接收/更新、可回退自动开机、已知信号质量与真实AI。

## 仍未解决及保存边界

偶发厂家启动0xFF、长期稳定性、连续采样证明、CDC与外部IO延迟缺项、自动开机和AI未完成。保存工作不代表这些项目通过。

本次没有发出关机命令。源码、固件、实验数据均在电脑磁盘上，断电不会使已保存资料消失；PL运行状态和RAM临时文件会丢。准备断电时先正常关机，再关闭电源。
'''
    (ROOT/'docs/handoff/STOP-P38-20261021.md').write_text(stop, encoding='utf-8')
    start_path = ROOT/'START-HERE.md'
    start = start_path.read_text('utf-8')
    banner = '**停工保存（2026-10-21）：** 已补齐P38全部64轮及8轮原始数据并核验逐轮SHA。先读[停工与再次上电步骤](docs/handoff/STOP-P38-20261021.md)，再按下方P38入口恢复。普通重启仍须重新初始化合并配置，不能复用旧boot。\n\n'
    start_path.write_text(start.replace('# 从这里恢复项目工作\n\n', '# 从这里恢复项目工作\n\n'+banner, 1), encoding='utf-8')
    resume_path = ROOT/'docs/handoff/RESUME-P38-20261021.md'
    resume = resume_path.read_text('utf-8')
    resume = resume.replace('其余63个完整raw仍只在板端RAM，断电会丢，不误报为电脑归档。',
        '停工时已将全部64轮及短测8轮原始数据补齐电脑归档，逐轮SHA核验通过；位置见[停工记录](STOP-P38-20261021.md)和p38_current。')
    resume_path.write_text(resume, encoding='utf-8')
    doc = ROOT/'docs/experiments/EXP-HW-028-periodic-RX-LCD.md'
    with doc.open('a', encoding='utf-8') as handle:
        handle.write('\n\n## 停工归档补充（2026-10-21）\n\n')
        handle.write('按用户要求保存全部工作，已将上文当时只在RAM的64轮及短测8轮原始数据完整归档电脑，逐轮SHA和偏移核验全部通过。原有“仅最后一轮归档”描述保留为当时状态；以[停工记录](../handoff/STOP-P38-20261021.md)和p38_current为最新保存状态。未新增功能验收、未关机。\n')
        handle.write('64轮归档：`'+full['archive_report']+'`；8轮归档：`'+short['archive_report']+'`。清单：`'+str(out/'cycles-64.json')+'`及`'+str(out/'cycles-8.json')+'`。\n')
        handle.write('16MiB数据首次gzip回读超过30秒，失败原件保留；随后独立确认gzip已结束、CRC/压缩与原始SHA及64个源文件一致，再完整回传核验。不是重新采样或修改原始记录。\n')
    files = set()
    def add(path):
        path = Path(path)
        if path.is_file() and path.suffix.lower() not in ('.lic', '.key', '.pem', '.pyc') and '__pycache__' not in path.parts:
            files.add(path.resolve())
    for name in ('src', 'host', 'embedded', 'board', 'experiments', 'tests', 'docs', 'fpga'):
        for path in (ROOT/name).rglob('*'): add(path)
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix.lower() in ('.md', '.json', '.toml', '.txt', '.cmd', '.ps1', '.py', '.yml', '.yaml', '.sh'):
            add(path)
    # All P36/37/38 local evidence, including ignored result files. No virtual
    # environment, tool installation or license file is bundled.
    for directory in (ROOT/'results').iterdir():
        if directory.is_dir() and directory != out and directory.name.startswith(('p36-', 'p37-', 'p38-')):
            for path in directory.rglob('*'): add(path)
    for name in ('cycles-64.json', 'cycles-8.json', 'executed.py'): add(out/name)
    bit = json.loads((ROOT/'results/p37-safe-bin-20261021T085630Z/report.json').read_text('utf-8'))
    for field in ('checkpoint', 'candidate_BD', 'DRP_source'):
        path = Path(bit[field]); data = path.read_bytes()
        if sha(data) != bit[field+'_sha256']: raise ValueError('external design changed: '+field)
        add(path)
    add(Path(bit['work'])/'project/combined.xpr')
    # Preserve direct file dependencies from machine-readable reports where
    # possible. Limit traversal to existing local result files, not log prose.
    def strings(value):
        if isinstance(value, str): yield value
        elif isinstance(value, dict):
            for item in value.values(): yield from strings(item)
        elif isinstance(value, list):
            for item in value: yield from strings(item)
    visited = set()
    while True:
        pending = [path for path in files if path.suffix == '.json' and path not in visited]
        if not pending: break
        for path in pending:
            visited.add(path)
            try: value = json.loads(path.read_text('utf-8'))
            except (ValueError, UnicodeError): continue
            for text in strings(value):
                if '\n' in text or len(text) > 400: continue
                normalized = text.replace('\\', '/')
                if not (normalized.startswith('results/') or normalized.lower().startswith(ROOT.as_posix().lower()+'/results/')):
                    continue
                candidate = Path(text)
                if not candidate.is_absolute(): candidate = ROOT/candidate
                if candidate.is_file() and candidate.resolve().is_relative_to((ROOT/'results').resolve()): add(candidate)
    manifest = dict(schema='rfsig.p38_stop_checkpoint.v1', created_utc=now,
                    full_cycles_manifest=full, short_cycles_manifest=short,
                    board_operations=False, board_shutdown_issued=False,
                    baseline_configuration_restored_automatically_on_powerup=False,
                    same_computer_original_directories_expected_for_resume=True,
                    files=[])
    zip_path = out/'checkpoint.zip'
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(files):
            if path.is_relative_to(ROOT.resolve()):
                name = 'rf-signal-lab/'+path.relative_to(ROOT.resolve()).as_posix()
            else:
                name = 'external-p37-design/'+path.relative_to(Path(bit['work']).resolve()).as_posix()
            data = path.read_bytes()
            manifest['files'].append(dict(archive_path=name, original_path=str(path), bytes=len(data), sha256=sha(data)))
            bundle.writestr(name, data)
        bundle.writestr('CHECKPOINT-MANIFEST.json', json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(zip_path) as bundle:
        if bundle.testzip() is not None: raise RuntimeError('ZIP CRC failure')
        for row in manifest['files']:
            if sha(bundle.read(row['archive_path'])) != row['sha256']: raise RuntimeError('ZIP member SHA failure')
    write_json(out/'manifest.json', manifest)
    report = dict(status='saved_complete_cycle_archives_and_verified_checkpoint_ZIP',
                  created_utc=now, zip_path=str(zip_path), zip_bytes=zip_path.stat().st_size,
                  zip_sha256=sha(zip_path.read_bytes()), file_count=len(manifest['files']),
                  all_zip_members_crc_and_sha_verified=True, board_shutdown_issued=False,
                  full_trial_cycles_saved=64, short_trial_cycles_saved=8,
                  current_state_source='last completed archive identity/idle checks; not a new shutdown')
    write_json(out/'report.json', report)
    print(out); print(report['status']); print('ZIP files verified: '+str(report['file_count']))


if __name__ == '__main__': main()
