"""Correct current acceptance scope using direct human physical-display feedback."""
from datetime import datetime,timezone
import json
from p32_session import ROOT
def main():
    path=ROOT/'TX-SOURCE-STATUS.json';state=json.loads(path.read_text('utf-8'))
    state['p43_current'].update(status='physical_LCD_cold_start_failed_pending_P44_diagnosis',
        user_power_cycle_observed=True,cold_RX_auto_start_verified=True,true_power_cycle_verified=False,
        physical_LCD_cold_start_accepted=False,physical_LCD_failure_report='results/p44-human-display-failure-20261022.json')
    state.update(status='physical_LCD_cold_start_failed_pending_P44_diagnosis',updated=datetime.now(timezone.utc).isoformat(),
        updated_note='P44: user reports fully black physical LCD; machine RX/framebuffer evidence does not prove physical display')
    path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (ROOT/'docs/experiments/EXP-HW-033-persistent-startup.md').open('a',encoding='utf-8') as f:
        f.write('\n## 用户实体屏幕反馈纠正（P44开始）\n\n用户回答冷启动显示检查为“黑屏或画面异常”，进一步明确“屏幕完全黑，没有明显背光”。因此本次实体屏幕显示不通过，整机冷启动验收撤回至待修复；板端自动RX、显存写入/回读、时钟检查仅在各自范围成立，不能推导物理屏正常。原始机器记录及旧检查点保留，当前状态以START-HERE、TX-SOURCE-STATUS.json及后续P44为准。用户观察时刻相对运行/停止未测量。\n')
    print('Physical-display acceptance corrected; original evidence preserved')
if __name__=='__main__':main()
