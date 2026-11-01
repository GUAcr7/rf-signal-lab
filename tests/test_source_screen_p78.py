"""Actual teammate IDs and critical no-RF selection/identity boundaries."""
import importlib.util
import json
from pathlib import Path
import pytest
from rfsig.tjc_protocol import ReturnParser,Event
from rfsig.source_screen import PanelSelection
from rfsig.board_session import discover_ports

def touch(button,page=0,edge=0):
    raw=bytes([0x65,page,button,edge,255,255,255])
    parser=ReturnParser();events=[]
    for byte in raw:events+=parser.feed(bytes([byte]))
    return events[0]

@pytest.mark.parametrize('button,index',[(1,0),(2,1),(3,2),(4,3)])
def test_actual_four_selection_ids_invalidate_apply(button,index):
    panel=PanelSelection();panel.checked()
    assert panel.touch(touch(button),1)=='select'
    assert panel.signal==index and panel.applied is None
    assert panel.touch(touch(6),2)=='unapplied'

def test_apply_start_request_and_stop_priority():
    p=PanelSelection()
    assert p.touch(touch(5),1)=='check' and p.applied is None
    p.checked()
    assert p.touch(touch(6),2)=='start'
    assert p.touch(touch(6),2.1) is None
    assert p.touch(touch(7),2.11)=='stop'
    assert p.touch(touch(7),2.12)=='stop'
    assert p.touch(touch(6),3)=='unapplied'

@pytest.mark.parametrize('event',[touch(1,edge=1),touch(1,page=1),touch(99),Event('text',0x70,b'6')])
def test_non_release_other_page_unknown_not_actions(event):
    p=PanelSelection();assert p.touch(event,1) is None
    assert p.signal==0 and p.applied is None

def test_duration_clamp_and_text_names_match_delivered_screen():
    p=PanelSelection()
    for n in range(20):p.touch(touch(8),n)
    assert p.seconds==8
    for n in range(20,40):p.touch(touch(9),n)
    assert p.seconds==60
    p.checked();assert p.fields('APPLIED')=={'t1':'APPLIED','t2':'SEL TONE','t4':'60'}
    assert all(len(v)<=10 for v in p.fields('NO RF TEST').values())

def candidates():
    return [dict(device='COM10',vid=0x0456,pid=0xB673,description='PlutoSDR Serial Console'),
            dict(device='COM80',vid=0x1a86,pid=0x7523,location='1-9'),
            dict(device='COM6',vid=0x1a86,pid=0x7523,location='1-4.3:x.3')]

def test_two_CH340_refused_without_bound_location_and_COM_renumbering_allowed():
    with pytest.raises(ValueError):discover_ports(candidates(),'usb-console')
    assert discover_ports(candidates(),'usb-console','1-9')=={'TX':'COM10','RX':'COM80'}
    with pytest.raises(ValueError):discover_ports(candidates(),'usb-console','missing')
    dup=candidates()+[dict(device='COM81',vid=0x1a86,pid=0x7523,location='1-9')]
    with pytest.raises(ValueError):discover_ports(dup,'usb-console','1-9')

def test_bound_topology_requires_unchanged_actual_Linux_proof(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('p78_test_control',Path(__file__).parents[1]/'host/board_control.py')
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);monkeypatch.setattr(c,'ROOT',tmp_path)
    (tmp_path/'configs').mkdir();(tmp_path/'results').mkdir()
    report=tmp_path/'results/proof.json'
    proof=dict(status='passed_P78_readonly_boards_and_teammate_screen_identity',serial_closed=True,
               boards={'RX':dict(profile_verified=True,identity='Linux Zynq-Tronlong')},
               resolved_ports={'RX':'COM80'},ports=candidates(),screen_candidate={'device':'COM6'})
    report.write_text(json.dumps(proof))
    config=dict(schema='rfsig.board_connections.v1',RX_USB_location='1-9',
                RX_USB_binding_evidence=dict(report='results/proof.json',sha256=c.sha(report)))
    (tmp_path/'configs/board-connections.json').write_text(json.dumps(config))
    assert c.load_rx_location()=='1-9'
    report.write_text(json.dumps({**proof,'serial_closed':False}))
    with pytest.raises(ValueError,match='changed'):c.load_rx_location()
    config['RX_USB_binding_evidence']['sha256']=c.sha(report)
    (tmp_path/'configs/board-connections.json').write_text(json.dumps(config))
    with pytest.raises(ValueError,match='not accepted'):c.load_rx_location()


def screen_with_response(after_write,before=b''):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'host'))
    from source_screen_link import Screen
    class FakePort:
        def __init__(self):self.pending=before
        @property
        def in_waiting(self):return len(self.pending)
        def read(self,n):
            data=self.pending[:n];self.pending=self.pending[n:];return data
        def write(self,data):self.pending+=after_write
    screen=object.__new__(Screen);screen.port=FakePort();screen.parser=ReturnParser();screen.touches=[]
    return screen

def test_text_truncation_live_regression_is_not_success():
    from rfsig.tjc_protocol import ProtocolError
    screen=screen_with_response(b'\x70CHECKED NO\xff\xff\xff')
    with pytest.raises(ProtocolError,match='mismatch'):
        screen.query('get t1.txt','text',b'CHECKED NO RF')

def test_old_text_is_not_a_fresh_heartbeat():
    from rfsig.tjc_protocol import ProtocolError
    screen=screen_with_response(b'',b'\x70READY\xff\xff\xff')
    with pytest.raises(ProtocolError,match='before a query'):
        screen.query('get t1.txt','text',b'READY')

def test_touch_interleaved_with_heartbeat_not_lost():
    screen=screen_with_response(b'\x65\x00\x07\x00\xff\xff\xff\x70READY\xff\xff\xff')
    assert screen.query('get t1.txt','text',b'READY')==b'READY'
    assert screen.touches[0][1].payload==b'\x00\x07\x00'

def test_reset_sleep_or_duplicate_query_results_fail_closed():
    from rfsig.tjc_protocol import ProtocolError
    for response in (b'\x88\xff\xff\xff',b'\x86\xff\xff\xff',
                     b'\x70READY\xff\xff\xff'*2):
        screen=screen_with_response(response)
        with pytest.raises(ProtocolError):screen.query('get t1.txt','text',b'READY')

def test_explicit_regression_driver_never_starts_before_READY_or_stops_before_RUNNING():
    from rfsig.source_screen_regression import ProtocolRegression
    p=ProtocolRegression()
    assert p.next_button('IDLE',False,0)==2
    assert p.next_button('IDLE',False,.4)==5
    assert p.next_button('CHECKING',True,1) is None
    assert p.next_button('READY',False,2)==6
    assert p.next_button('STARTING',True,3) is None
    assert p.next_button('RUNNING',True,4) is None
    assert p.next_button('RUNNING',True,6.9) is None
    assert p.next_button('RUNNING',True,7)==7
    assert p.next_button('STOPPING',True,8) is None
    assert p.next_button('IDLE',False,9) is None
    assert p.index==1
