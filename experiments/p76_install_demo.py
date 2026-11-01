"""Separate rollback-capable competition-demo profile, one ordinary reboot.

Uses the tested P70 installer unchanged for hardware/startup operations.
Release basis is P75 controlled RF acceptance; no new independent score claimed.
"""
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub


def generate():
    parent=ROOT/'experiments/p70_install_profile.py'
    if sha(parent)!=sha(ROOT/'results/p70-boot-20261026T031221Z/executed.py'):
        raise ValueError('tested P70 installer changed')
    text=parent.read_text(encoding='utf-8')
    start=text.index("    review_path=ROOT/")
    end=text.index('    with control.operation_lock():',start)
    text=text[:start]+'''    review_path=ROOT/'results/p75-review-20261026T102124Z/report.json';review=read(review_path)
    if review['status']!='passed_P75_prospective_RF_history_phase_replay_metrics_and_cleanup' or not all(g['passed'] for g in review['gates']):raise ValueError('passed actual P75 RF required')
    trial_path=ROOT/review['trial'];trial=read(trial_path)
    if sha(trial_path)!=review['trial_sha256']:raise ValueError('P75 trial changed')
    build_path=ROOT/trial['build'];build=read(build_path)
    if sha(build_path)!=trial['build_sha256'] or sha(ROOT/build['binary'])!=build['binary_sha256']:raise ValueError('P75 build changed')
    review={**review,'build':rel(build_path),'build_sha256':sha(build_path),'binary_sha256':build['binary_sha256']}
    for p,h in build['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('candidate input changed '+p)
    for name,count in (('p76-controller-tests-20261026.xml',75),('p76-startup-tests-20261026.xml',15)):
        cases=list(ET.parse(ROOT/'results'/name).getroot().iter('testcase'))
        if len(cases)!=count or any(list(c.iter(k)) for c in cases for k in ('error','failure','skipped')):raise ValueError('offline acceptance '+name)
    config=ROOT/'configs/receiver-profile.json'
    previous_selection=config.read_bytes()
    selection=read(config)
    if selection['report']!='results/p70-boot-20261026T031221Z/report.json' or selection['report_sha256']!='d51ea1587a6a3e55bd1a4462537ff967a91377cbd72adcf1bca4674d904faf18':raise ValueError('only accepted P70 may be replaced once')
'''+text[end:]
    # Installer stage/profile labels only; the fixed P75 references above remain.
    text=text.replace('p70-install','p76-install').replace("('p70-boot-'","('p76-boot-'")
    text=text.replace('rfsig.receiver_profile.p70.v1','rfsig.receiver_profile.p76.v1')
    text=text.replace("ROOT/'results/p70-active.json'","ROOT/'results/p76-active.json'")
    text=text.replace('P70_','P76_').replace('passed_P70_','passed_P76_').replace('failed_or_unconfirmed_P70_','failed_or_unconfirmed_P76_')
    text=text.replace('passed_P76_warm_boot_autonomous_ROI_display','passed_P76_warm_boot_autonomous_phase_AI_display')
    text=text.replace("stage='/tmp/p35-p70-'","stage='/tmp/p35-p76-'").replace('/etc/rcS.d/.p70-switch','/etc/rcS.d/.p76-switch')
    text=sub(text,"        (out/'executed.py').write_bytes(Path(__file__).read_bytes());c.save();print(out,flush=True)",
        "        (out/'executed.py').write_bytes(Path(__file__).read_bytes())\n        (out/'previous-selection.json').write_bytes(previous_selection)\n        c.record.update(release_scope='controlled_competition_demo',previous_selection_sha256=sha(out/'previous-selection.json'),independent_accuracy_newly_claimed=False)\n        c.save();print(out,flush=True)")
    text=sub(text,'            selected_profile(ROOT,old,provenance)',
        '            control.load_profile()')
    text=sub(text,"previous_profile_report=provenance['accepted_boot_report']",
        "previous_profile_report=rel(Path(provenance['accepted_boot_report']))")
    return text,parent


if __name__=='__main__':
    code,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p76-install-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-install.py';path.write_text(code,encoding='utf-8')
    write(out/'report.json',dict(parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path),
        entry_sha256=sha(Path(__file__)),release_scope='controlled_competition_demo',
        user_scope='user accepted core display/AI as sufficient and asked to continue finalization; no further algorithm optimization'))
    exec(compile(code,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
