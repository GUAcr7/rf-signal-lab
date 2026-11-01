"""Full-check equivalence and fail-closed framing, no board IO."""
from pathlib import Path
import sys,json,base64,gzip
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'host'))
import fast_panel_control as fast
from rfsig.board_session import require_rx_control

@pytest.fixture
def snapshot():
    root=Path(__file__).parents[1]
    old=json.loads((root/'results/p59-p79-session-archive-20261027T132602604111Z/report.json').read_text('utf-8'))['after_RX']
    profile,_=fast.control.load_profile()
    values=dict(schema='rfsig.rx_control_snapshot.v1',complete='yes',boot_before=old['boot_id'],boot_after=old['boot_id'],
                taint=old['taint'],names='\n'.join('__D__'+p+':'+n+'__E__' for n,p in old['IIO_names'].items()),
                rx_buffer=old['RX_buffer'],tx_buffer=old['TX_buffer'],selected_wrapper_sha256=old['selected_wrapper_sha256'],
                init_boot_marker=old['init_boot_marker'],exit_code=old['exit_code'] or '',owned_pid=old['owned_pid'] or '',
                owned_timeout_argv='\n'.join(old['owned_timeout_argv']),kernel_tail=old['kernel_tail'])
    values.update({'rf_'+k:v for k,v in old['RF'].items()})
    values.update({'scan_'+str(i):v for i,v in enumerate(old['RX_scans'])})
    values.update({'sha_'+k:v for k,v in old['profile_hashes'].items()})
    for a,b in [('progress','progress'),('later_progress','later_progress'),('ai','AI'),('summary','summary')]:
        values[a]=json.dumps(old[b]) if old[b] is not None else ''
    return values,profile,old

def frame(values):
    raw=b''.join(k.encode()+b'\0'+v.encode('utf-8')+b'\0' for k,v in values.items())
    return base64.b64encode(gzip.compress(raw)).decode()+'\n__P46_deadbeef__:0\n'

def test_complete_snapshot_matches_recorded_stopped_checks(snapshot):
    values,profile,old=snapshot
    got=fast.decode_snapshot(frame(values),profile,old['identity'])
    got['session_state']=fast.classify_rx(got)
    for key in ('boot_id','taint','RF','RF_matches','RX_buffer','TX_buffer','RX_scans','profile_hashes','profile_verified',
                'selected_wrapper_sha256','owned_timeout_pid','owned_timeout_argv','AI','progress','summary','session_state'):
        assert got[key]==old[key],key
    require_rx_control(got,running=False)

@pytest.mark.parametrize('patch',[{'complete':'no'},{'boot_after':'00000000-0000-0000-0000-000000000000'},
                                 {'schema':'unknown'},{'progress':'not JSON'}])
def test_missing_or_wrong_snapshot_refused(snapshot,patch):
    values,profile,old=snapshot
    with pytest.raises(ValueError):fast.decode_snapshot(frame({**values,**patch}),profile,old['identity'])

@pytest.mark.parametrize('key,value',[('taint','1'),('rf_in_voltage_rf_bandwidth','1'),('sha_monitor','0'*64),
                                    ('selected_wrapper_sha256','0'*64),('scan_0','1'),
                                    ('kernel_tail','Oops: test fault')])
def test_all_original_safety_fields_still_gate_control(snapshot,key,value):
    values,profile,old=snapshot;got=fast.decode_snapshot(frame({**values,key:value}),profile,old['identity'])
    with pytest.raises(ValueError):require_rx_control(got,running=False)

def test_partial_compressed_transfer_is_not_a_valid_snapshot(snapshot):
    values,profile,old=snapshot;payload=frame(values)
    with pytest.raises(Exception):fast.decode_snapshot(payload[:len(payload)//2],profile,old['identity'])
    del values['taint']
    with pytest.raises(ValueError):fast.decode_snapshot(frame(values),profile,old['identity'])

def test_owned_handles_reused_within_action_and_closed_on_error():
    from contextlib import contextmanager
    c=object.__new__(fast.FastPanelController);opened=[];closed=[]
    @contextmanager
    def fake(role):
        opened.append(role)
        try:yield (role,'identity')
        finally:closed.append(role)
    c._uncached_board=fake
    with pytest.raises(RuntimeError):
        with c.session():
            with c.board('TX') as a:
                with c.board('TX') as b:assert a==b
            with c.board('RX'):pass
            assert opened==['TX','RX'] and closed==[]
            raise RuntimeError('synthetic action failure')
    assert closed==['RX','TX'] and c._handle_scope is None
