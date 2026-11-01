"""Read idle-board AD9361 reset GPIO binding and live DT bytes; no pin writes."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import struct

from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expected-boot',required=True);args=p.parse_args()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p40-reset-readback-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],expected_boot=args.expected_boot,read_only=True,
        reset_GPIO_written=False,SPI_register_access=False,physical_waveform_measured=False,root_cause_closed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        def identity():
            if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=args.expected_boot or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity/taint changed')
        identity()
        if re.search(r'arm-latest|arm[-_]rx|arm[-_]panel|iio_readdev|p35-p39-\d+/a',board.command('ps -ef')):raise ValueError('active receiver')
        board.command('/etc/rcS.d/S99board --check-rf');board.command('s=/sys/bus/spi/devices')
        text=board.command('for d in $s/spi*;do echo $d;cat $d/modalias;done')
        matches=re.findall(r'(/sys/bus/spi/devices/spi\d+\.\d+)\r?\nspi:ad9361\r?$',text,re.M)
        if len(matches)!=1:raise ValueError('AD9361 SPI node ambiguous')
        r['SPI_device']=matches[0];board.command('s='+matches[0]);r['SPI_driver']=board.command('readlink -f $s/driver')
        r['live_DT_node']=board.command('readlink -f $s/of_node');board.command('n=$(readlink -f $s/of_node)')
        def cells(prop,count):
            text=board.command('echo __DATA__;od -An -tx1 $n/'+prop+';echo __END__')
            frame=re.search(r'(?m)^__DATA__\r?\n([0-9a-f \r\n]+)^__END__\r?$',text)
            if not frame:raise ValueError('DT property frame unreadable: '+prop)
            raw=bytes.fromhex(frame[1]);r[prop+'_hex']=raw.hex()
            if len(raw)!=count*4:raise ValueError('unexpected property cells: '+prop)
            return list(struct.unpack('>'+'I'*count,raw))
        r['reset_GPIO_cells']=cells('reset-gpios',3);r['SPI_max_frequency_Hz']=cells('spi-max-frequency',1)[0]
        if r['reset_GPIO_cells'][1:]!=[100,0] or r['SPI_max_frequency_Hz']!=10000000:raise ValueError('live reset/SPI contract differs')
        r['SPI_cpha_present']=bool(re.search(r'^CPHA_PRESENT\r?$',board.command('test -e $n/spi-cpha && echo CPHA_PRESENT'),re.M))
        if not r['SPI_cpha_present']:raise ValueError('live CPHA absent')
        r['gpio_debug']=board.command('cat /sys/kernel/debug/gpio')
        r['reset_debug_lines']=[line for line in r['gpio_debug'].splitlines() if re.search(r'gpio-\d+\s+\([^\r\n]*\breset\b',line)]
        board.command('g=/sys/class/gpio');r['gpiochip_bases']=board.command('for d in $g/gpiochip*;do echo $d;cat $d/base $d/ngpio;done')
        identity();r['status']='live_reset_binding_and_idle_level_collected_not_waveform_proof'
    except Exception as exc:r.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status'])
    return 0 if r['status'].startswith('live_') else 1


if __name__=='__main__':raise SystemExit(main())
