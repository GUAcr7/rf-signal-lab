"""Save preparation while physical power-cycle input is still required."""
from datetime import datetime,timezone
from p32_session import ROOT
from p45_checkpoint import checkpoint,read,write,sha,rel

def main():
    prep=ROOT/'results/p45-power-cycle-prepare-20261022T102927Z/report.json'
    capture=ROOT/'results/p43-passive-power-on-20261022T103021Z/report.json'
    enable=ROOT/'results/p43-enabled-20261022T102622Z/report.json'
    if not read(prep)['halt_observed'] or not read(capture)['serial_closed']:raise ValueError('halt/capture not final')
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p45-waiting-checkpoint-%Y%m%dT%H%M%S%fZ')
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    current=state['p45_current'];current.update(status='saved_preparation_waiting_user_physical_power_cycle',
        updated_utc=now.isoformat(),checkpoint=rel(out/'report.json'),enable_report=rel(enable),
        poweroff_record=rel(prep),first_passive_capture=rel(capture),new_cold_boot_after_fix_verified=False,
        record='docs/experiments/EXP-HW-035-cold-display-verification.md',resume='docs/handoff/RESUME-P45-20261022.md',
        user_power_cycle_reply_received=False,board_shutdown_issued=True,halt_observed=True,serial_closed=True,
        last_observed_boot=read(prep)['expected_boot'])
    state.update(authoritative_current_field='p45_current',status=current['status'],updated=now.isoformat(),
        record=current['record'],updated_note='P45 preparation saved, normal receiver halt confirmed, waiting user physical power action; no controlled cold acceptance yet')
    state['session_stop']=dict(active=False,superseded_by='p45_current',board_shutdown_issued=True,halt_observed=True,record=rel(prep))
    write(state_path,state);write(ROOT/'results/p45-active.json',current)
    with (ROOT/current['record']).open('a',encoding='utf-8') as f:
        f.write('\n## 断电准备保存\n\n新板正常关机已确认System halted，记录`'+rel(prep)+'`。首个180秒被动记录窗口`'+rel(capture)+'`发送0字节、收到0字符；尚无用户电源操作回复，因此这仅表示没有捕获到重新上电，不是启动失败或冷启动通过。主机未重新起流、重启或热装驱动。原始数据已归档，新增相关25项门禁通过`results/p45-final-host-gates-20261022.xml`。当前等待用户只将新板断电约10秒再接电，旧板不动。\n')
    result=checkpoint('p45-waiting-checkpoint',dict(enable=enable,poweroff=prep,first_capture=capture),destination=out)
    print(result)
if __name__=='__main__':main()
