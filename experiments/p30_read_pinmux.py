"""Read receiver identity and pinctrl diagnostics. No GPIO/register/RF writes."""
from datetime import datetime,timezone
import json
from p22_acquire_comparison import Console,ROOT


def main():
    out=ROOT/'results'/('p30-pinmux-readback-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',read_only=True,stages=[],gpio_writes=False,register_writes=False,RF_writes=False)
    console=None
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        console=Console('COM8',report,save)
        identity=console.command('uname -a')
        if 'Zynq-Tronlong' not in identity:raise RuntimeError('receiver identity not confirmed')
        commands=['cat /proc/sys/kernel/random/boot_id','cat /etc/board-mode',
            'ls /sys/kernel/debug/pinctrl',
            'find /proc/device-tree -name "*pinctrl*"',
            'find /sys/kernel/debug/pinctrl -name pinconf-pins',
            'cat /sys/kernel/debug/pinctrl/*/pinconf-pins',
            'cat /sys/kernel/debug/pinctrl/*/pinmux-pins',
            '/etc/rcS.d/S99board --check-rf']
        report['observations']=[]
        for command in commands:
            if len(command)>72:raise RuntimeError('console width limit')
            output=console.command(command)
            report['observations'].append(dict(command=command,output=output));save()
        report['status']='read_only_diagnostics_archived'
    except Exception as error:report.update(status='failed_or_unavailable',error=repr(error))
    finally:
        if console:console.close()
        save();print(out);print(report['status'])


if __name__=='__main__':main()
