"""Preserve the exact failed controller provenance and its minimal procedure fix."""
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    out=ROOT/'results/p57-protocol-correction-20261024T094100Z'
    before=out/'generator-before.py';first=ROOT/'results/p57-attachment-20261024T093720Z/report.json';old=read(first)
    failure=ROOT/'results/p57-review-20261024T094313Z/report.json';failed=read(failure)
    second=ROOT/'results/p57-attachment-20261024T094526Z/report.json';new=read(second)
    if sha(before)!=old['inputs']['generator']['sha256'] or failed['status']!='failed_or_unconfirmed_runtime_AI_review' or 'source-off background observations retained' not in failed['error']:raise ValueError('correction provenance differs')
    oldboot=read(ROOT/old['inputs']['boot']['path']);newboot=read(ROOT/new['inputs']['boot']['path'])
    if oldboot['installed_files_sha256']!=newboot['installed_files_sha256']:raise ValueError('boot profile changed during procedure correction')
    write(out/'report.json',dict(status='preserved_insufficient_background_failure_and_six_second_procedure_fix',board_operations=False,
        failure=dict(path=rel(failure),sha256=sha(failure)),first_attachment=dict(path=rel(first),sha256=sha(first)),
        generator_before=dict(path=rel(before),sha256=sha(before)),second_attachment=dict(path=rel(second),sha256=sha(second)),
        generator_after=dict(path='experiments/p57_prepare_attachment.py',sha256=sha(ROOT/'experiments/p57_prepare_attachment.py')),
        native_binary_changed=False,model_changed=False,acceptance_thresholds_changed=False,
        fix='append six seconds of source-off monitoring after verified DDS zero and before owned RX stop; repeat on a new ordinary boot'))
    print(rel(out/'report.json'))
if __name__=='__main__':main()
