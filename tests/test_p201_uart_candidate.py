from pathlib import Path
import pytest
from rfsig.p201_uart import candidate_sources,enabled_dts

BASE=Path(__file__).resolve().parents[1]/'fpga/vendor-baseline/source/plutosdr-fw/hdl/projects/pzp201'
def original():return tuple((BASE/n).read_text() for n in ('system_bd.tcl','system_top.v','system_constr.xdc'))

def test_preserves_console_rf_and_adds_only_two_3v3_pins():
    bd,top,xdc=original();b,t,x=candidate_sources(bd,top,xdc)
    assert b.startswith(bd) and x.startswith(xdc)
    assert 'CONFIG.PCW_UART1_UART1_IO "MIO 12 .. 13"' in b
    assert 'sys_ps7/UART0_TX' in b and 'sys_ps7/UART0_RX' in b
    assert '.ext_uart_tx (ext_uart_tx)' in t and '.ext_uart_rx (ext_uart_rx)' in t
    assert 'PACKAGE_PIN E17 IOSTANDARD LVCMOS33' in x
    assert 'PACKAGE_PIN E18 IOSTANDARD LVCMOS33' in x
    assert 'LVCMOS18' in x  # original RF constraints retained

@pytest.mark.parametrize('pin',['E17','E18'])
def test_rejects_occupied_pins(pin):
    bd,top,xdc=original()
    with pytest.raises(ValueError,match='occupied'):candidate_sources(bd,top,xdc+'\nPACKAGE_PIN '+pin)

def test_rejects_reapplication_and_existing_uart0():
    with pytest.raises(ValueError):candidate_sources(*candidate_sources(*original()))
    bd,top,xdc=original()
    with pytest.raises(ValueError):candidate_sources(bd+'\nPCW_UART0',top,xdc)

@pytest.mark.parametrize('anchor',['module system_top (','system_wrapper i_system_wrapper ('])
def test_rejects_missing_or_duplicate_top_anchor(anchor):
    bd,top,xdc=original()
    for changed in (top.replace(anchor,''),top+anchor):
        with pytest.raises(ValueError):candidate_sources(bd,changed,xdc)

def test_dts_changes_keep_console_on_physical_uart1():
    source='/dts-v1/; / { amba { serial@e0000000 {}; serial@e0001000 {}; }; };'
    candidate=enabled_dts(source)
    assert candidate.startswith(source)
    assert 'serial0 = "/amba/serial@e0001000"' in candidate
    assert 'serial1 = "/amba/serial@e0000000"' in candidate
    assert 'stdout-path = "/amba/serial@e0001000:115200n8"' in candidate

@pytest.mark.parametrize('source',['/ {};','amba {serial@e0000000 {};};','amba {serial@e0000000 {};serial@e0001000 {};serial1="other";};'])
def test_unknown_tree_or_existing_alias_rejected(source):
    with pytest.raises(ValueError):enabled_dts(source)
