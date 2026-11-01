"""Prepare a new complete startup profile on the PC; never install or reboot."""
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from p32_session import ROOT
from p43_boot_templates import render
from p36_build_rx_full import posix


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',type=Path,required=True);args=p.parse_args()
    suite=read(args.suite)
    if suite['status']!='passed_P48_finite_display_units_candidate_and_original_startup_rearmed' or not suite['startup_selection_rearmed']:raise ValueError('finished rearmed P48 suite required')
    build_path=ROOT/suite['inputs']['build']['path'];build=read(build_path)
    if sha(build_path)!=suite['inputs']['build']['sha256'] or build['display_revision']!='p48':raise ValueError('P48 build changed')
    binary=Path(build['binary']);monitor=binary.read_bytes()
    if sha(binary)!=build['binary_sha256']:raise ValueError('native ELF changed')
    cycle_path=ROOT/'results/p43-boot-cycle-20261022T031333Z/report.json';cycle=read(cycle_path)
    prep_path=Path(cycle['preparation_report']);prep=read(prep_path)
    if prep['status']!='passed_persistent_shell_and_stop_gates_not_hardware_boot' or prep['test_count']!=13:raise ValueError('tested shell renderer required')
    for name,digest in prep['inputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('shell input changed')
    old=(cycle_path.parent/'files/bringup').read_text('ascii')
    values={k:re.search(r'^'+k+r'=(\S+)\r?$',old,re.M)[1] for k in ('BIT','BIT_SHA','DTBO','DTBO_SHA')}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p48-profile-'+stamp);out.mkdir(exist_ok=False)
    directory='/etc/p43-'+stamp;files=render(directory,suite['expected_boot'],build['binary_sha256'],values['BIT'],values['BIT_SHA'],values['DTBO'],values['DTBO_SHA'])
    files['monitor']=monitor;(out/'files').mkdir()
    for name,data in files.items():(out/'files'/name).write_bytes(data)
    checks=[]
    for name in ('boot','bringup','control','run'):
        result=subprocess.run(['wsl.exe','--exec','sh','-n',posix(out/'files'/name)],capture_output=True,timeout=20)
        checks.append(dict(name=name,exit_code=result.returncode))
        if result.returncode:raise ValueError('prepared shell syntax failed')
    report=dict(status='prepared_P48_complete_startup_profile_PC_only_not_installed',suite=str(args.suite.resolve()),suite_sha256=sha(args.suite),
        build=str(build_path),build_sha256=sha(build_path),parent_profile=str(cycle_path),parent_profile_sha256=sha(cycle_path),
        original_shell_preparation=str(prep_path),original_shell_preparation_sha256=sha(prep_path),
        proposed_directory=directory,armed_boot=suite['expected_boot'],files_sha256={k:sha(out/'files'/k) for k in files},
        syntax_checks=checks,board_operations=False,installed_on_board=False,warm_boot_P48_verified=False,cold_boot_P48_verified=False,
        notes='Install only as a new complete profile after fresh identity/idle checks; do not overwrite the existing accepted profile monitor.')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status'])


if __name__=='__main__':main()
