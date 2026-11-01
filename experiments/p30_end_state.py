"""Read current identities and idle buffers after the saved P30 checkpoint."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from p22_acquire_comparison import Console,ROOT
from p26_restore_rx_profile import parse_attribute_frame


def main():
    state=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))['p30_integration']
    out=ROOT/'results'/('p30-end-state-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',created_utc=datetime.now(timezone.utc).isoformat(),stages=[],
        board_RF_writes=False,firmware_writes=False,reboots=False,read_only=True,boards={})
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def value(board,path):
        board.command('a='+path)
        return parse_attribute_frame(board.command('echo __P26_VALUE__$(cat $a)__P26_END__'))
    save();board=None
    try:
        for port,name,expected_boot in [('COM9','Linux pzp201',state['tx_boot_id']),('COM8','Zynq-Tronlong',state['rx_boot_id'])]:
            board=Console(port,report,save)
            if name not in board.command('uname -a'):raise RuntimeError('wrong board '+port)
            boot=board.command('cat /proc/sys/kernel/random/boot_id')
            if expected_boot not in boot:raise RuntimeError('board rebooted again '+port)
            if port=='COM9':
                directory=state['tx_recovery_directory']
                if not re.fullmatch(r'/tmp/p12-source-stage-p30-[0-9]{6}',directory):raise ValueError('unrecognized RAM directory')
                board.command('cd '+directory+'/stage')
                inspect=board.command('./arm/arm-tx-source --inspect')
                if 'INSPECT_PASS read_only=true no_buffers_created=true' not in inspect:raise RuntimeError('TX inspect incomplete')
                processes=board.command('ps')
                if any('arm-tx-source' in line for line in processes.splitlines()):raise RuntimeError('unexpected TX process')
                report['boards'][port]=dict(boot_id=expected_boot,inspect_pass=True,no_TX_process_observed=True)
            else:
                board.command('/etc/rcS.d/S99board --check-rf')
                mode=value(board,'/etc/board-mode')
                fpga=value(board,'/sys/class/fpga_manager/fpga0/state')
                if mode!='rf' or fpga!='operating':raise RuntimeError('unexpected board mode/state')
                board.command('p=/sys/bus/iio/devices')
                names=board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
                pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',names)
                by_name={n:p for p,n in pairs}
                if not all(n in by_name for n in ['ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc']):raise RuntimeError('missing IIO named device')
                board.command('cd '+by_name['ad9361-phy'])
                expected={'in_voltage_sampling_frequency':'30720000','in_voltage_rf_bandwidth':'18000000',
                    'out_altvoltage0_RX_LO_frequency':'2450000000','in_voltage0_gain_control_mode':'manual',
                    'in_voltage0_hardwaregain':'0.000000 dB','in_voltage0_rf_port_select':'A_BALANCED'}
                attributes={key:value(board,key) for key in expected}
                if attributes!=expected:raise RuntimeError('RX attributes changed')
                board.command('cd '+by_name['cf-ad9361-lpc'])
                enabled=value(board,'buffer/enable')
                scan=[value(board,f'scan_elements/in_voltage{i}_en') for i in range(4)]
                if enabled!='0' or scan!=['0']*4:raise RuntimeError('receiver buffer/scan remains active')
                processes=board.command('ps -ef')
                if any(re.search(r'p27-rx|arm-rx-capture|iio_readdev',line) for line in processes.splitlines()):raise RuntimeError('unexpected receive process')
                report['boards'][port]=dict(boot_id=expected_boot,mode=mode,fpga_state=fpga,named_devices=by_name,
                    RX_attributes=attributes,buffer_enable=enabled,scan_after_release=scan,no_RX_process_observed=True)
            board.close();board=None;save()
        report['status']='both_original_firmware_sessions_idle_and_RX_profile_readback_verified'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if board:board.close()
        report['serial_handles_closed']=True
        report['ended_utc']=datetime.now(timezone.utc).isoformat();save()
    print(out);print(report['status'])
    if 'error' in report:print(report['error'])
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
