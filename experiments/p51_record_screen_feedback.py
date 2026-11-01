"""Record the human's late finished-screen observation; host files only."""
from datetime import datetime,timezone
from p45_checkpoint import ROOT,rel,sha,write,read

def main():
    trial=ROOT/'results/p51-board-20261023T151444Z/report.json'
    summary=read(trial)['native_summary']
    if summary['status']!='pass' or summary['reason']!='duration_complete':
        raise ValueError('completed trial required')
    now=datetime.now(timezone.utc)
    out=ROOT/'results'/now.strftime('p51-screen-feedback-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    write(out/'report.json',dict(
        status='user_confirmed_finished_screen_after_completed_trial',
        recorded_utc=now.isoformat(),timestamp_kind='recorded_at_not_observation_time',
        trial=rel(trial),trial_sha256=sha(trial),source='direct_user_conversation_reply',
        initial_answer='亮着，但不再变化',
        followup_question='刚才“亮着但不再变化”是现在看到的吗？半小时程序已正常结束。请看屏幕顶部文字，更接近哪一种？',
        followup_answer='现在看到 RX FINISHED／RX STOPPED 等结束提示',
        illuminated_finished_screen_confirmed=True,active_period_motion_confirmed=False,
        active_period_motion_status='not_independently_observed_in_this_trial',
        interpretation='Stopped counters match completed trial; no inference of physical motion during active period.',
        board_operations=False))
    print(out/'report.json')

if __name__=='__main__':main()
