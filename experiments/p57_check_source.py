"""Recheck existing bounded source against a new RX boot; never starts TX."""
import argparse,re
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
from p46_known_source import GUARD_SHA

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--boot',required=True,type=Path);args=ap.parse_args();boot=read(args.boot)
    from p58_boot_contract import validate_boot
    validate_boot(args.boot)
    parent=ROOT/'results/p52-restored-20261024T080358Z/report.json';old=read(parent)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-source-%Y%m%dT%H%M%SZ');out.mkdir()
    r={k:old[k] for k in ('expected_boot','files_sha256','references','source_peak_component_counts','remote_directory')}
    r.update(status='checking',stages=[],RX_expected_boot=boot['expected_boot'],RX_boot_report=rel(args.boot),RX_boot_report_sha256=sha(args.boot),
        source_parent=rel(parent),source_parent_sha256=sha(parent),serial_closed=False,RF_operations=False,RF_attribute_writes=False,PL_changes=False,
        existing_files_reused=True,new_upload_performed=False)
    def save():write(out/'report.json',r)
    b=None;save()
    try:
        b=Console('COM9',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p57src_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=old['expected_boot'] or b.value('/proc/sys/kernel/tainted')!='0' or 'Linux pzp201' not in b.command('uname -a'):raise ValueError('source identity changed; explicit restore required')
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        for name in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):
            if b.value(n[name]+'/buffer/enable')!='0':raise ValueError('source DMA active')
        b.command('cd '+old['remote_directory'])
        for name,digest in old['files_sha256'].items():
            b.command('v='+old['remote_directory']+'/'+name);found=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
            if found!=[digest]:raise ValueError('source SHA changed '+name)
        if old['files_sha256']['guard']!=GUARD_SHA:raise ValueError('guard differs')
        r['inspect']=b.command('./guard --inspect',timeout=15)
        if 'tx_lo=2450000000' not in r['inspect'] or 'tx0_hardwaregain=-10.000000 dB' not in r['inspect']:raise ValueError('source RF settings changed')
        if any(not re.search(r'^dds'+str(i)+r'_raw=0(?:\.0+)?\r?$',r['inspect'],re.M) for i in range(8)):raise ValueError('source DDS not zero')
        for name in ('tone','bpsk','qpsk','qam16'):
            b.command('h='+old['files_sha256'][name]);text=b.command('./guard --check '+name+' 131072 $h')
            if 'INPUT_CHECK_PASS samples=131072' not in text:raise ValueError('source input check failed')
        r['status']='passed_existing_guard_sources_rechecked_for_new_RX_boot_no_TX'
    except Exception as e:r.update(status='failed_source_recheck',error=repr(e))
    finally:
        if b:
            try:b.command('stty echo');b.command('PS1=$p57src_prompt')
            except Exception as e:r['TTY_restore_error']=repr(e)
            b.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
