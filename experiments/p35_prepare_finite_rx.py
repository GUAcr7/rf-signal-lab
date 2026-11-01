"""Set only the documented RX test settings on an idle, identified current boot.

No transmitter, FPGA, overlay, PWM or boot operations. Initial and final RF
configuration are recorded; this is intentionally separate from the executable
whose acceptance requires RF settings remain unchanged during cancellation.
"""
import argparse
from datetime import datetime,timezone
import json,re
from p32_session import ROOT,BoardConsole

ATTRS=['in_voltage_sampling_frequency','in_voltage_rf_bandwidth',
 'out_altvoltage0_RX_LO_frequency','in_voltage0_gain_control_mode',
 'in_voltage0_hardwaregain','in_voltage0_rf_port_select']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    args=parser.parse_args()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-finite-rx-prep-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record=dict(status='preflight',stages=[],RF_RX_attribute_writes=True,
        TX_operations=False,FPGA_operations=False,expected_boot=args.expected_boot)
    def save():(out/'report.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    board=None
    try:
        board=BoardConsole('COM8',record,save);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        if board.value('/proc/sys/kernel/random/boot_id')!=args.expected_boot:
            raise RuntimeError('boot changed')
        if board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('kernel tainted')
        processes=board.command('ps -ef')
        if re.search(r'arm-tx-source|p27-rx|arm-rx-capture|iio_readdev|p33-cancel',processes):
            raise RuntimeError('active experiment observed')
        board.command('p=/sys/bus/iio/devices')
        names=board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        paths={n:p for p,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',names)}
        board.command('cd '+paths['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):
            raise RuntimeError('RX not idle')
        board.command('cd '+paths['ad9361-phy'])
        record['before']={a:board.value(a) for a in ATTRS}
        if record['before']['in_voltage_sampling_frequency']!='30720000' or record['before']['in_voltage_rf_bandwidth']!='18000000':
            raise RuntimeError('unreviewed sample rate or bandwidth')
        for command in ['echo manual > in_voltage0_gain_control_mode',
                'echo 0 > in_voltage0_hardwaregain',
                'echo 2450000000 > out_altvoltage0_RX_LO_frequency']:
            board.command(command)
        record['after']={a:board.value(a) for a in ATTRS}
        expected=dict(zip(ATTRS,['30720000','18000000','2450000000','manual','0.000000 dB','A_BALANCED']))
        if record['after']!=expected:raise RuntimeError('RX setting readback differs')
        record['status']='bounded_RX_test_configuration_read_back'
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        record['serial_closed']=True;save();print(out);print(record['status'])
    return 0 if record['status'].startswith('bounded_') else 1

if __name__=='__main__':raise SystemExit(main())
