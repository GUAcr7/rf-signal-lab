"""Publish the current bounded trial pointer; PC files only."""
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write,rel

def main():
    report=sorted((ROOT/'results').glob('p51-board-*/report.json'))[-1];trial=read(report)
    if trial['status']!='native_running' or not trial['progress_samples']:raise ValueError('running trial required')
    state=read(ROOT/'TX-SOURCE-STATUS.json')
    if trial['expected_boot']!=state['p50_current']['expected_boot']:raise ValueError('baseline boot differs')
    current=dict(status='P51_bounded_30min_trial_running',updated_utc=datetime.now(timezone.utc).isoformat(),
        report=rel(report),expected_boot=trial['expected_boot'],RX_idle=False,serial_closed=False,
        startup_selection_paused=True,current_enable=state['p50_current']['current_enable'],
        record='docs/experiments/EXP-P51-stability-and-ai-input.md',resume='docs/handoff/RESUME-P51-20261023.md')
    state.update(status=current['status'],authoritative_current_field='p51_current',p51_current=current,
        updated=current['updated_utc'],record=current['record'],status_note='P51有界接收正在运行，COM8独占；归档后必须恢复启动选择。P50 idle为历史。')
    write(ROOT/'TX-SOURCE-STATUS.json',state);write(ROOT/'results/p51-active.json',current)

if __name__=='__main__':main()
