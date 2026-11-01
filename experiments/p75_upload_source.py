"""Use exactly the audited fixed-entry RAM upload with a frozen new package.

No RF transmission; preserve standard source-active provenance/boot checks.
"""
import argparse,inspect,sys,textwrap
from pathlib import Path
from p45_checkpoint import ROOT,read,sha,rel
sys.path.insert(0,str(ROOT/'host'))
import board_control as control


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plan',required=True,type=Path);a=ap.parse_args()
    plan=read(a.plan)
    if plan['status']!='frozen_before_P75_RF_acquisition' or sha(ROOT/plan['source'])!=plan['source_sha256']:
        raise ValueError('frozen source plan required')
    method=textwrap.dedent(inspect.getsource(control.Controller.prepare_source))
    old="source_path = ROOT / 'results/p54-plan-20261024T042837Z/2026102315/report.json'"
    if method.count(old)!=1:raise ValueError('audited source selector changed')
    method=method.replace(old,"source_path = ROOT / "+repr(plan['source']))
    with control.operation_lock():
        c=control.Controller('prepare-source');namespace=vars(control).copy()
        (c.out/'p75-executed-upload.py').write_text(method,encoding='utf-8')
        (c.out/'p75-entry.py').write_bytes(Path(__file__).read_bytes())
        c.record.update(P75_plan=rel(a.plan),P75_plan_sha256=sha(a.plan),RF_transmissions=0)
        try:
            c.status();exec(compile(method,'<fixed RAM upload new package>','exec'),namespace)
            namespace['prepare_source'](c,c.record['boards']['TX'])
            control.finish_record(c,True)
        except Exception as exc:control.finish_record(c,False,exc)
        print(c.out);print(c.record['status'])


if __name__=='__main__':main()
