import hashlib
from pathlib import Path

import pytest

from rfsig.rf_link_budget import ConductedLink, evaluate_conducted_link, validate_link_plan


def fixture_plan(tmp_path):
    # Fictional fixtures deliberately are not P201/FMCOMMS3 specifications.
    evidence = tmp_path / "fictional-test.txt"
    evidence.write_text("unit-test placeholder, never a hardware power specification", encoding="utf-8")
    proof = {"path": str(evidence.resolve()), "locator": "test fixture only",
             "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
    current = dict(board_model="PUZHI PZSDR P201", serial="fixture-123",
                   sample_rate_hz=30720000, tx_dma_sample_rate_hz=30720000, tx_lo_hz=2450000000,
                   tx_rf_bandwidth_hz=18000000, tx_hardwaregain_db=-30.0, tx_rf_port="A")
    waveform = dict(name="tone", raw_sha256="b" * 64, sample_rate_hz=30720000,
                    baseband_support_hz=[960000, 960000])
    plan = dict(schema="rfsig.conducted_tx_review.v1", connection="conducted_50ohm_no_antenna",
                package_sha256="a" * 64, waveform_sha256="b" * 64, waveform_name="tone",
                duration_seconds=1, expected_tx=current.copy(), physical_connection_checked=True,
                tx_pa_included_in_power_spec=True, unused_tx_ports_handled_per_manual=True,
                components={name: dict(model="fictional-test", impedance_ohm=50,
                                       min_frequency_hz=1e6, max_frequency_hz=6e9)
                            for name in ("tx_connector", "rx_connector", "cable", "attenuator")},
                evidence={name: proof.copy() for name in ("tx_connector_power", "rx_connector_recommended_input",
                          "attenuator_rating", "cable_connectors", "physical_connection")},
                power_budget=dict(tx_peak_upper_dbm=10., rx_recommended_peak_max_dbm=-10.,
                                  attenuation_min_db=35., cable_loss_min_db=0.,
                                  attenuator_input_rating_dbm=20., required_headroom_db=5.))
    return plan, current, waveform


def validate(plan, current, waveform):
    return validate_link_plan(plan, package_sha256="a" * 64, waveform=waveform, current_tx=current)


def test_budget_conservative_peak_not_dac_counts():
    result = evaluate_conducted_link(ConductedLink(10, -10, 35, 0, 20, 5))
    assert result["rx_peak_upper_dbm"] == -25
    assert result["headroom_db"] == 15
    assert result["power_budget_passed"]
    assert not evaluate_conducted_link(ConductedLink(10, -10, 10, 0, 20, 5))["power_budget_passed"]
    assert not evaluate_conducted_link(ConductedLink(10, -10, 35, 0, 9, 5))["power_budget_passed"]


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), "10"])
def test_budget_rejects_missing_or_nonfinite(value):
    with pytest.raises(ValueError):
        evaluate_conducted_link(ConductedLink(value, -10, 35, 0, 20, 5))


def test_bound_plan_and_evidence(tmp_path):
    plan, current, waveform = fixture_plan(tmp_path)
    result = validate(plan, current, waveform)
    assert result["rf_transmitted"] is False
    assert result["rf_support_hz"] == [2450960000, 2450960000]
    assert result["duration_seconds"] == 1
    Path(plan["evidence"]["tx_connector_power"]["path"]).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Evidence"):
        validate(plan, current, waveform)


@pytest.mark.parametrize("field,value", [("sample_rate_hz", 4000000), ("serial", "another-board"),
                                        ("tx_hardwaregain_db", -10), ("tx_lo_hz", 2400000000)])
def test_live_config_change_rejected(tmp_path, field, value):
    plan, current, waveform = fixture_plan(tmp_path)
    current[field] = value
    with pytest.raises(ValueError, match="differs"):
        validate(plan, current, waveform)


@pytest.mark.parametrize("change", ["no_check", "wireless", "wrong_package", "wrong_waveform",
                                    "long_run", "bad_rating", "missing_input", "wrong_frequency", "wrong_fs"])
def test_incomplete_or_stale_review_rejected(tmp_path, change):
    plan, current, waveform = fixture_plan(tmp_path)
    if change == "no_check": plan["physical_connection_checked"] = False
    elif change == "wireless": plan["connection"] = "antennas"
    elif change == "wrong_package": plan["package_sha256"] = "c" * 64
    elif change == "wrong_waveform": waveform["raw_sha256"] = "c" * 64
    elif change == "long_run": plan["duration_seconds"] = 61
    elif change == "bad_rating": plan["power_budget"]["attenuator_input_rating_dbm"] = 0
    elif change == "missing_input": del plan["evidence"]["rx_connector_recommended_input"]
    elif change == "wrong_frequency": plan["components"]["attenuator"]["max_frequency_hz"] = 1e9
    elif change == "wrong_fs": waveform["sample_rate_hz"] = 4000000
    with pytest.raises(ValueError): validate(plan, current, waveform)


def test_waveform_outside_current_filter_rejected(tmp_path):
    plan, current, waveform = fixture_plan(tmp_path)
    waveform["baseband_support_hz"] = [10e6, 10e6]
    with pytest.raises(ValueError, match="does not fit"):
        validate(plan, current, waveform)


@pytest.mark.parametrize("field", ["components", "evidence", "expected_tx", "power_budget"])
def test_null_sections_rejected_cleanly(tmp_path, field):
    plan, current, waveform = fixture_plan(tmp_path)
    plan[field] = None
    with pytest.raises(ValueError): validate(plan, current, waveform)


@pytest.mark.parametrize("field", ["path", "sha256", "locator"])
def test_null_evidence_fields_rejected_cleanly(tmp_path, field):
    plan, current, waveform = fixture_plan(tmp_path)
    plan["evidence"]["tx_connector_power"][field] = None
    with pytest.raises(ValueError): validate(plan, current, waveform)


@pytest.mark.parametrize("dma_rate", [None, 3840000, 30720000.0])
def test_dma_rate_requires_explicit_integer_bypass_readback(tmp_path, dma_rate):
    plan, current, waveform = fixture_plan(tmp_path)
    current["tx_dma_sample_rate_hz"] = dma_rate
    plan["expected_tx"]["tx_dma_sample_rate_hz"] = dma_rate
    with pytest.raises(ValueError): validate(plan, current, waveform)
