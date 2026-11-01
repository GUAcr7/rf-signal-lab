import json

import pytest

from rfsig.tx_package import PROFILES, link_plan_template, prepare_tx_package, verify_tx_package
from rfsig.rf_link_budget import validate_link_plan


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setitem(PROFILES, "test", dict(sample_rate_hz=4000000,
        samples_per_symbol=16, symbol_count=64, offset_hz=500000))
    path = tmp_path / "package"
    prepare_tx_package(path, "test")
    return path


def edit_manifest(path, mutation):
    file = path / "manifest.json"
    manifest = json.loads(file.read_text(encoding="utf-8"))
    mutation(manifest)
    file.write_text(json.dumps(manifest), encoding="utf-8")


def test_package_roundtrip_and_pending_template(package):
    result = verify_tx_package(package)
    assert result["rf_transmitted"] is False
    assert len(result["waveforms"]) == 5
    assert all(w["regenerated_reference_exact"] for w in result["waveforms"])
    assert result["waveforms"][0]["observed_peak_hz"] == 500000
    assert result["waveforms"][1]["observed_peak_hz"] == -500000
    with pytest.raises(ValueError):
        validate_link_plan(link_plan_template(package), package_sha256=result["package_sha256"],
                           waveform={}, current_tx={})


def test_does_not_overwrite(package):
    with pytest.raises(FileExistsError): prepare_tx_package(package)


@pytest.mark.parametrize("field,value", [("sample_rate_hz", 8000000), ("offset_hz", 250000),
    ("requested_dac_peak_counts", 256), ("samples_per_symbol", 32),
    ("baseband_support_hz", [0, 0]), ("raw_bytes", 4)])
def test_metadata_mistake_rejected(package, field, value):
    edit_manifest(package, lambda m: m["waveforms"][2].__setitem__(field, value))
    with pytest.raises(ValueError): verify_tx_package(package)


def test_raw_corruption_rejected(package):
    path = package / "qpsk.iq16le"
    raw = bytearray(path.read_bytes()); raw[0] ^= 16; path.write_bytes(raw)
    with pytest.raises(ValueError, match="checksum"): verify_tx_package(package)


@pytest.mark.parametrize("name", ["../outside", "C:/outside", "sub\\outside"])
def test_package_does_not_read_external_paths(package, name):
    edit_manifest(package, lambda m: m["waveforms"][0].__setitem__("raw_file", name))
    with pytest.raises(ValueError): verify_tx_package(package)


def test_reference_spec_disagreement_rejected(package):
    edit_manifest(package, lambda m: m["waveforms"][3]["waveform_reference"].__setitem__("sample_rate_hz", 1))
    with pytest.raises(ValueError): verify_tx_package(package)
