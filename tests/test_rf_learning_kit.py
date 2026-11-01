"""Use preserved RF bytes to test package integrity and offline GUI callbacks.

Skipped when the optional local P47 delivery is absent (results are gitignored).
These are programmatic Agg checks, not claimed physical mouse interaction.
"""
import hashlib
import json
from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pytest
from host.rf_learning_kit.data_api import load_kit,inside
from host.rf_learning_kit.viewer import LearningView

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def kit():
    state=ROOT/'results/p47-active.json'
    if not state.is_file():pytest.skip('P47 optional local raw-data delivery is absent')
    path=Path(json.loads(state.read_text('utf-8'))['directory'])
    if not path.is_dir():pytest.skip('P47 delivery directory is unavailable')
    return path


@pytest.fixture(scope='module')
def loaded(kit):return load_kit(kit)


@pytest.fixture
def view(kit,loaded,tmp_path):
    v=LearningView(loaded[1],kit,output_root=tmp_path/'exports')
    yield v
    v.timer.stop();plt.close(v.fig)


def rehash(kit,name):
    p=kit/'manifest.json';manifest=json.loads(p.read_text('utf-8'));path=kit/name
    row=next(v for v in manifest['files'] if v['path']==name)
    row.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    p.write_text(json.dumps(manifest),encoding='utf-8')


def test_every_original_buffer_is_decoded_exactly_and_remains_separate(loaded):
    manifest,records=loaded
    assert manifest['raw_original_bytes']==4*1048576
    assert manifest['independent_ML_benchmark_eligible'] is False
    for record in records.values():
        assert record.iq.shape==(4,65536)
        assert record.iq_counts.shape==(4,65536,2)
        assert np.array_equal(record.iq.real,record.iq_counts[:,:,0])
        assert np.array_equal(record.iq.imag,record.iq_counts[:,:,1])
        with pytest.raises(ValueError):record.iq[0,0]=0


def test_detects_damaged_distributed_file_before_using_it(kit,tmp_path):
    clone=tmp_path/'copy';shutil.copytree(kit,clone)
    (clone/'cases/bpsk.npz').write_bytes(b'damaged')
    with pytest.raises(ValueError,match='hash/size'):load_kit(clone)


def test_decoded_and_complex_arrays_must_match_original_even_if_rehashed(kit,tmp_path):
    clone=tmp_path/'copy';shutil.copytree(kit,clone);path=clone/'cases/bpsk.npz'
    with np.load(path,allow_pickle=False) as f:values={k:f[k].copy() for k in f.files}
    values['iq_counts'][0,0,0]+=1;values['iq'][0,0]+=1
    np.savez_compressed(path,**values);rehash(clone,'cases/bpsk.npz')
    with pytest.raises(ValueError,match='decoding differs'):load_kit(clone)


def test_rejects_relabeling_as_independent_ML_benchmark(kit,tmp_path):
    clone=tmp_path/'copy';shutil.copytree(kit,clone);path=clone/'manifest.json'
    m=json.loads(path.read_text('utf-8'));m['independent_ML_benchmark_eligible']=True
    path.write_text(json.dumps(m),encoding='utf-8')
    with pytest.raises(ValueError,match='learning-only'):load_kit(clone)


def test_paths_cannot_escape_package(tmp_path):
    with pytest.raises(ValueError):inside(tmp_path,'../outside')
    with pytest.raises(ValueError):inside(tmp_path,'C:\\outside')


def test_pause_resume_and_end_of_file_are_finite(view):
    assert view.replay.latest is None
    view.toggle();assert view.step() is True
    assert view.replay.next_frame==1
    view.toggle();view.step();assert view.replay.next_frame==1
    view.toggle()
    while view.replay.state=='running':view.replay.advance()
    assert view.replay.next_frame==64 and view.replay.state=='finished'
    view.step();view.toggle();assert view.replay.next_frame==64
    view.reset();assert view.replay.state=='paused' and view.replay.latest is None
    assert view.replay.history.rows_received==0


def test_switching_DMA_and_label_clears_history_and_preserves_correct_samples(view,loaded):
    view.toggle();view.step();view.slider.set_val(2)
    assert view.block==1 and view.replay.state=='paused' and view.replay.history.rows_received==0
    assert np.array_equal(view.replay.iq,loaded[1]['bpsk'].iq[1])
    view.selector.set_active(2)
    assert view.key=='qpsk' and view.replay.latest is None
    assert np.array_equal(view.replay.iq,loaded[1]['qpsk'].iq[1])
    view.toggle();view.step();before=view.replay.next_frame
    axes=len(view.fig.axes)
    for _ in range(3):view.draw()
    view.check.set_active(0)
    assert view.full_band and view.replay.next_frame==before
    assert len(view.fig.axes)==axes


def test_export_retains_selected_original_frame_and_scope(view):
    assert view.export() is None
    view.select_block(4);view.toggle();view.step();out=view.export()
    assert (out/'screen.png').is_file()
    meta=json.loads((out/'report.json').read_text('utf-8'))
    assert meta['hardware_contacted'] is False and meta['ai_connected'] is False
    assert meta['source']['selected_DMA_zero_based']==3
    assert meta['source']['label_source']=='known_transmitter_configuration'
    with np.load(out/'analysis.npz',allow_pickle=False) as f:
        assert np.array_equal(f['iq'],view.records['bpsk'].iq[3,:1024])
