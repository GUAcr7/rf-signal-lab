"""Read both boards before known-source testing. No RF, firmware or startup writes."""
from datetime import datetime,timezone
import json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p46-preflight-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='reading',stages=[],boards={},RF_operations=False,RF_attribute_writes=False,PL_changes=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save();board=None
    try:
        for port,identity in [('COM9','Linux pzp201'),('COM8','Zynq-Tronlong')]:
            item={};r['boards'][port]=item;folder=out/port;folder.mkdir()
            board=BoardConsole(port,r,save);board.port=AuditPort(board.port,folder);board.shell()
            item['uname']=board.command('uname -a')
            if identity not in item['uname']:raise ValueError('wrong board '+port)
            item['boot_id']=board.value('/proc/sys/kernel/random/boot_id');item['taint']=board.value('/proc/sys/kernel/tainted')
            item['processes']=board.command('ps' if port=='COM9' else 'ps -eww -o pid,ppid,args')
            if re.search(r'arm-tx-source|iio_readdev|/run/p42-\d+/monitor',item['processes']):raise ValueError('experiment already active')
            board.command('ir=/sys/bus/iio/devices');text=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
            names={n:d for d,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)};item['IIO_names']=names
            if not {'ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc'}<=names.keys():raise ValueError('IIO names incomplete')
            item['buffers']={}
            for name in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):
                board.command('cd '+names[name]);item['buffers'][name]=board.value('buffer/enable')
                if item['buffers'][name]!='0':raise ValueError('active DMA '+port)
            board.command('cd '+names['ad9361-phy']);item['RF']={}
            attrs=['in_voltage_sampling_frequency','in_voltage_rf_bandwidth','out_altvoltage0_RX_LO_frequency',
                'out_altvoltage1_TX_LO_frequency','out_voltage0_hardwaregain','out_voltage0_rf_port_select',
                'out_voltage_sampling_frequency','out_voltage_rf_bandwidth','in_voltage0_gain_control_mode','in_voltage0_hardwaregain','in_voltage0_rf_port_select']
            for attr in attrs:item['RF'][attr]=board.value(attr)
            if port=='COM9':
                item['RAM_stages']=board.command('ls -d /tmp/p12-source-stage-* 2>/dev/null || true')
                item['TX_binaries']=board.command('find /tmp -maxdepth 5 -name arm-tx-source 2>/dev/null')
                board.command('cd '+names['cf-ad9361-dds-core-lpc'])
                item['DDS_raw']=board.command('for n in out_altvoltage*_raw;do echo $n;cat $n;done')
            item['kernel_tail']=board.command('dmesg | tail -n 65',timeout=15)
            if item['taint']!='0':raise ValueError('tainted kernel '+port)
            board.close();board=None;save()
        r['status']='read_only_both_boards_identified_DMA_idle'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('read_only_') else 1
if __name__=='__main__':raise SystemExit(main())
