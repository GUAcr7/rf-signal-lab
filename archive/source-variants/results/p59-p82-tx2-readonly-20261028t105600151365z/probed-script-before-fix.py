"""Read-only inventory for a proposed dual-TX demonstration, never enables TX2."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'host'), str(ROOT / 'src'), str(ROOT / 'experiments')]
import board_control as control


def main():
    with control.operation_lock():
        c = control.Controller('p82-TX2-readonly')
        print(c.out, flush=True)
        c.record.update(RF_transmissions=0, RF_attribute_writes=False,
                        TX2_enabled_by_this_run=False, PL_changes=False,
                        scope='inventory only, no dual-output functionality or physical port mapping acceptance')
        try:
            c.status()
            tx = c.record['boards']['TX']
            control.require_tx_off(tx)
            with c.board('TX') as (b, identity):
                fresh = c.inspect('TX', b, identity)
                control.require_tx_off(fresh)
                if fresh['boot_id'] != tx['boot_id']:
                    raise ValueError('TX rebooted during read-only inventory')
                phy = fresh['IIO_names']['ad9361-phy']
                dac = fresh['IIO_names']['cf-ad9361-dds-core-lpc']
                c.record['TX2_phy_attributes'] = {
                    name: c.optional(b, phy + '/' + name) for name in
                    ('out_voltage1_hardwaregain', 'out_voltage1_rf_port_select',
                     'out_voltage1_sampling_frequency', 'out_voltage1_rf_bandwidth')}
                b.command('d=' + dac)
                b.command('cd $d/scan_elements')
                c.record['TX_scan_attributes'] = b.command('for n in *;do echo "$n=$(cat $n)";done')
                after = c.inspect('TX', b, identity)
                control.require_tx_off(after)
                if after['boot_id'] != fresh['boot_id'] or after['RF'] != fresh['RF']:
                    raise ValueError('TX identity or RF settings changed')
                c.record['after_TX'] = after
            c.record.update(status='passed_P82_readonly_TX_channel_inventory',
                            next_gate='physical routing plus duplicated I/Q and dual-channel gain/stop/cleanup need separate validation')
        except Exception as error:
            c.record.update(status='failed_or_unconfirmed_P82_readonly_inventory', error=repr(error))
        finally:
            c.record['serial_closed'] = True
            c.save()
            print(c.record['status'], flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
