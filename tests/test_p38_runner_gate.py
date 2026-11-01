import sys
import argparse
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'experiments'))
from p38_run_rx_panel import detached_framebuffer_console
from p36_retrieve_file import remote_path
from p36_fb_snapshot_run import accepted_panel_parent


def test_kernel_prefix_precedes_framebuffer_name():
    text = '/sys/class/vtconsole/vtcon0\r\n(S) dummy device\r\n1\r\n/sys/class/vtconsole/vtcon1\r\n(M) frame buffer device\r\n0\r\n'
    assert detached_framebuffer_console(text)
    assert not detached_framebuffer_console(text.replace('device\r\n0', 'device\r\n1'))


def test_dummy_console_or_duplicate_framebuffer_does_not_authorize_draw():
    assert not detached_framebuffer_console('/sys/class/vtconsole/vtcon0\n(S) dummy device\n0\n')
    frame = '/sys/class/vtconsole/vtcon1\n(M) frame buffer device\n0\n'
    assert not detached_framebuffer_console(frame+frame)


def test_periodic_archive_paths_only_accept_bounded_cycle_files():
    for cycle in (0, 63):
        path = f'/tmp/p35-p38-094451/data/cycle-{cycle:03}/iq-packed.bin.gz'
        assert remote_path(path) == path
    for path in ('/tmp/p35-p38-094451/data/cycle-064/iq-packed.bin.gz',
                 '/tmp/p35-p38-094451/data/../iq-packed.bin.gz',
                 '/tmp/p35-p38-094451/data/cycle-000/iq-packed.bin.gz;reboot'):
        with pytest.raises(argparse.ArgumentTypeError):
            remote_path(path)


def test_framebuffer_archive_requires_same_boot_completed_idle_parent():
    parent = dict(schema='rfsig.p38_board.v1',
                  status='passed_periodic_RX_and_LCD_draw_with_independent_idle_readback',
                  expected_boot='current', independent_final_idle_verified=True,
                  native_completion_unconfirmed=False)
    assert accepted_panel_parent(parent, 'current')
    assert not accepted_panel_parent(parent, 'other')
    assert not accepted_panel_parent(dict(parent, native_completion_unconfirmed=True), 'current')
    assert not accepted_panel_parent(dict(parent, independent_final_idle_verified=False), 'current')
    assert accepted_panel_parent(dict(status='passed_frozen_sparse_analysis_and_framebuffer_draw_only', expected_boot='current'), 'current')


def test_latest_prefix_archive_and_completed_same_boot_draw():
    path='/tmp/p35-p39-141200/data/last-display-packed.bin.gz'
    assert remote_path(path)==path
    with pytest.raises(argparse.ArgumentTypeError):remote_path(path.replace('last-display-packed','../other'))
    parent=dict(schema='rfsig.p39_board.v1',status='passed_latest_buffer_RX_LCD_and_independent_idle_readback',
                independent_final_idle_verified=True,native_completion_unconfirmed=False,expected_boot='current')
    assert accepted_panel_parent(parent,'current')
    assert not accepted_panel_parent(dict(parent,native_completion_unconfirmed=True),'current')


def test_autonomous_parent_requires_restored_fresh_init_and_idle():
    parent=dict(schema='rfsig.p41_autonomous_once.v1',
        status='passed_autonomous_once_boot_RX_LCD_and_independent_idle_readback',
        expected_boot='current',independent_final_idle_verified=True,native_completion_unconfirmed=False,
        guard_restored=True,fresh_empty_boot_verified=True,monitor_started_by_board_init=True,
        serial_closed=True,PL_programming_attempts=1,overlay_apply_attempts=1)
    assert accepted_panel_parent(parent,'current')
    assert not accepted_panel_parent(parent,'different')
    for key in ('guard_restored','fresh_empty_boot_verified','monitor_started_by_board_init','independent_final_idle_verified','serial_closed'):
        assert not accepted_panel_parent(dict(parent,**{key:False}),'current')
    assert not accepted_panel_parent(dict(parent,PL_programming_attempts=True),'current')
    assert not accepted_panel_parent(dict(parent,overlay_apply_attempts=2),'current')
