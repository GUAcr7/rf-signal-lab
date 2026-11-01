"""Checksummed, offline-only files for a future bounded P201 signal source."""

import hashlib
import json
from pathlib import Path

import numpy as np

from rfsig.tx_waveforms import make_tx_waveform, pack_tx_iq_le16


SCHEMA = "rfsig.tx_package.v1"
PROFILES = {
    "existing30m72": dict(sample_rate_hz=30720000, samples_per_symbol=128,
                          symbol_count=1024, offset_hz=960000),
    "planned4m250k": dict(sample_rate_hz=4000000, samples_per_symbol=16,
                          symbol_count=2048, offset_hz=500000),
    "planned4m125k": dict(sample_rate_hz=4000000, samples_per_symbol=32,
                          symbol_count=1024, offset_hz=500000),
}


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def prepare_tx_package(directory, profile="existing30m72", *, seed=20261016, peak=512):
    if profile not in PROFILES:
        raise ValueError("Unknown source profile")
    target = Path(directory).resolve()
    target.mkdir(parents=True, exist_ok=False)
    spec = PROFILES[profile]
    waves = []
    names = [("tone-positive", "tone", spec["offset_hz"]),
             ("tone-negative", "tone", -spec["offset_hz"]),
             ("bpsk", "BPSK", spec["offset_hz"]),
             ("qpsk", "QPSK", spec["offset_hz"]),
             ("qam16", "16QAM", spec["offset_hz"])]
    for name, modulation, offset in names:
        wave = make_tx_waveform(modulation, **{**spec, "offset_hz": offset},
                                seed=seed, digital_peak_counts=peak)
        raw_path = target / (name + ".iq16le")
        raw_path.write_bytes(pack_tx_iq_le16(wave.iq))
        reference_path = target / (name + ".reference.npz")
        np.savez(reference_path, logical_iq=wave.iq, storage_iq=wave.storage_iq,
                 bits=wave.bits, symbols=wave.symbols, taps=wave.taps)
        half_support = 0 if modulation == "tone" else 1.35 * spec["sample_rate_hz"] / spec["samples_per_symbol"] / 2
        item = dict(name=name, modulation=modulation, seed=seed, sample_rate_hz=spec["sample_rate_hz"],
                    samples_per_symbol=spec["samples_per_symbol"], symbol_count=spec["symbol_count"],
                    symbol_rate_hz=None if modulation == "tone" else spec["sample_rate_hz"] / spec["samples_per_symbol"],
                    sample_count=int(wave.iq.size), offset_hz=offset, requested_dac_peak_counts=peak,
                    raw_file=raw_path.name, reference_file=reference_path.name,
                    raw_sha256=file_hash(raw_path), reference_sha256=file_hash(reference_path),
                    raw_bytes=raw_path.stat().st_size, format="LE int16 I,Q; signed12 logical DAC code multiplied by 16",
                    baseband_support_hz=[offset - half_support, offset + half_support],
                    support_note="Tone location or ideal RRC support; finite-filter sidelobes exist; not measured 99% OBW",
                    mean_logical_digital_power=float(np.mean(np.abs(wave.iq) ** 2)),
                    actual_dac_component_peak_counts=int(max(np.max(np.abs(wave.iq.real)), np.max(np.abs(wave.iq.imag)))),
                    waveform_reference=wave.reference)
        waves.append(item)
    manifest = dict(schema=SCHEMA, profile=profile, source_kind="generated_tx_reference_not_rf",
                    rf_transmitted=False, actual_tx_verified=False, digital_units="DAC counts, not dBm",
                    sample_rate_is_planned=True, requires_live_rate_readback=True,
                    note="This package neither connects hardware nor configures a radio. No run script auto-starts TX.",
                    waveforms=waves)
    _json(target / "manifest.json", manifest)
    verification = verify_tx_package(target)
    _json(target / "verification.json", verification)
    return manifest, verification


def _local_file(root, filename):
    if not isinstance(filename, str) or Path(filename).name != filename or ":" in filename or "\\" in filename:
        raise ValueError("Package members must be local basenames")
    path = root / filename
    if path.resolve().parent != root or not path.is_file():
        raise ValueError("Package member missing or outside package")
    return path


def verify_tx_package(directory):
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("source_kind") != "generated_tx_reference_not_rf":
        raise ValueError("Unknown TX package or source kind")
    if manifest.get("rf_transmitted") is not False:
        raise ValueError("Offline package cannot claim RF transmission")
    waves = manifest.get("waveforms", [])
    if len(waves) != 5 or len({w["name"] for w in waves}) != 5:
        raise ValueError("Expected five different source waveforms")
    files = set()
    results = []
    for item in waves:
        paths = [_local_file(root, item[key]) for key in ("raw_file", "reference_file")]
        if any(p.name in files for p in paths):
            raise ValueError("Duplicate package member")
        files.update(p.name for p in paths)
        raw, reference = paths
        if file_hash(raw) != item["raw_sha256"] or file_hash(reference) != item["reference_sha256"]:
            raise ValueError("TX package checksum mismatch")
        n = item["sample_count"]
        if type(n) is not int or not 4 <= n <= 1048576 or raw.stat().st_size != n * 4 or item["raw_bytes"] != n * 4:
            raise ValueError("TX sample count or byte size mismatch")
        reference_meta = item.get("waveform_reference", {})
        for key in ("modulation", "sample_rate_hz", "sample_count", "seed", "offset_hz"):
            if reference_meta.get(key) != item.get(key):
                raise ValueError(f"Waveform metadata differs from reference: {key}")
        if reference_meta.get("digital_peak_counts") != item["requested_dac_peak_counts"]:
            raise ValueError("DAC peak differs from reference")
        # Recreate from independently stored specification, then compare the exact
        # quantized bytes. Metadata-only mistakes cannot silently redefine rate.
        regenerated = make_tx_waveform(item["modulation"], sample_rate_hz=item["sample_rate_hz"],
            samples_per_symbol=item["samples_per_symbol"], symbol_count=item["symbol_count"],
            seed=item["seed"], offset_hz=item["offset_hz"],
            digital_peak_counts=item["requested_dac_peak_counts"],
            rolloff=reference_meta["rrc_rolloff"] if item["modulation"] != "tone" else .35,
            span_symbols=reference_meta["rrc_span_symbols"] if item["modulation"] != "tone" else 10)
        if regenerated.reference != reference_meta or pack_tx_iq_le16(regenerated.iq) != raw.read_bytes():
            raise ValueError("TX waveform differs from regenerated reference")
        expected_support = ([item["offset_hz"], item["offset_hz"]] if item["modulation"] == "tone"
                            else regenerated.reference["theoretical_rrc_support_hz"])
        if item["baseband_support_hz"] != expected_support:
            raise ValueError("Frequency support differs from waveform reference")
        codes = np.fromfile(raw, dtype="<i2").reshape(n, 2).astype(np.int32)
        if np.any(codes & 15):
            raise ValueError("TX storage low four bits must be zero")
        logical = codes // 16
        if np.max(np.abs(logical)) > 2047:
            raise ValueError("TX logical counts exceed symmetric signed12 limit")
        iq = logical[:, 0] + 1j * logical[:, 1]
        with np.load(reference, allow_pickle=False) as saved:
            np.testing.assert_array_equal(iq, saved["logical_iq"])
            np.testing.assert_array_equal(codes[:, 0] + 1j * codes[:, 1], saved["storage_iq"])
            for key in ("bits", "symbols", "taps"):
                np.testing.assert_array_equal(saved[key], getattr(regenerated, key))
        np.testing.assert_allclose(float(np.mean(np.abs(iq) ** 2)), item["mean_logical_digital_power"], rtol=1e-14)
        row = dict(name=item["name"], samples=n, bytes=n * 4, roundtrip_exact=True,
                   regenerated_reference_exact=True,
                   mean_logical_digital_power=float(np.mean(np.abs(iq) ** 2)),
                   low_four_bits_zero=True, source_kind="generated_not_received")
        if item["modulation"] == "tone":
            spectrum = np.abs(np.fft.fft(iq)) ** 2
            k = int(np.argmax(spectrum))
            observed = float(np.fft.fftfreq(n, d=1 / item["sample_rate_hz"])[k])
            if abs(observed - item["offset_hz"]) > item["sample_rate_hz"] / n * 1e-9:
                raise ValueError("Quantized tone FFT frequency differs from requested coherent bin")
            row.update(observed_peak_hz=observed, expected_peak_hz=item["offset_hz"])
        results.append(row)
    return dict(status="offline_package_roundtrip_and_tone_frequency_passed_rf_pending",
                package_sha256=file_hash(root / "manifest.json"), waveforms=results,
                rf_transmitted=False, live_rf_accuracy_verified=False)


def link_plan_template(directory):
    """Deliberately incomplete: missing hardware facts cannot pass review."""
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    wave = manifest["waveforms"][0]
    return dict(schema="rfsig.conducted_tx_review.v1", connection="conducted_50ohm_no_antenna",
                package_sha256=file_hash(root / "manifest.json"), waveform_sha256=wave["raw_sha256"],
                waveform_name=wave["name"], duration_seconds=5,
                physical_connection_checked=False, tx_pa_included_in_power_spec=False,
                unused_tx_ports_handled_per_manual=False,
                expected_tx=dict(board_model="PUZHI PZSDR P201", serial=None,
                                 sample_rate_hz=wave["sample_rate_hz"], tx_dma_sample_rate_hz=None, tx_lo_hz=None,
                                 tx_rf_bandwidth_hz=None, tx_hardwaregain_db=None, tx_rf_port=None),
                components={name: dict(model=None, impedance_ohm=50, min_frequency_hz=None, max_frequency_hz=None)
                            for name in ("tx_connector", "rx_connector", "cable", "attenuator")},
                evidence={name: dict(path=None, sha256=None, locator=None)
                          for name in ("tx_connector_power", "rx_connector_recommended_input", "attenuator_rating",
                                       "cable_connectors", "physical_connection")},
                power_budget=dict(tx_peak_upper_dbm=None, rx_recommended_peak_max_dbm=None,
                                  attenuation_min_db=None, cable_loss_min_db=None,
                                  attenuator_input_rating_dbm=None, required_headroom_db=None))
