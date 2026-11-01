"""A conservative conducted-RF link calculation, separate from DAC counts.

No device access and no guessed P201/FMCOMMS3 connector power limits. Values
must describe the *external connectors*, including an on-board PA if present.
"""

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import re


@dataclass(frozen=True)
class ConductedLink:
    tx_peak_upper_dbm: float
    rx_recommended_peak_max_dbm: float
    attenuation_min_db: float
    cable_loss_min_db: float
    attenuator_input_rating_dbm: float
    required_headroom_db: float


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number from connector specifications")
    return float(value)


def _mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _digest(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be a lower-case SHA256 digest")
    return value


def evaluate_conducted_link(link: ConductedLink) -> dict:
    values = {key: _finite(value, key) for key, value in asdict(link).items()}
    for key in ("attenuation_min_db", "cable_loss_min_db", "required_headroom_db"):
        if values[key] < 0:
            raise ValueError(f"{key} cannot be negative")
    if values["required_headroom_db"] <= 0:
        raise ValueError("A positive, explicitly chosen headroom is required")
    rx_upper = (values["tx_peak_upper_dbm"] - values["attenuation_min_db"]
                - values["cable_loss_min_db"])
    headroom = values["rx_recommended_peak_max_dbm"] - rx_upper
    # No credit for cable loss before the attenuator: it may be directly at TX.
    rating_margin = values["attenuator_input_rating_dbm"] - values["tx_peak_upper_dbm"]
    return {
        **values, "rx_peak_upper_dbm": rx_upper,
        "headroom_db": headroom, "attenuator_rating_margin_db": rating_margin,
        "power_budget_passed": headroom >= values["required_headroom_db"] and rating_margin >= 0,
        "note": "A calculation, not a measurement or authorization. Not an absolute RF power calibration.",
    }


def validate_link_plan(plan: dict, *, package_sha256: str, waveform: dict,
                       current_tx: dict, verify_evidence=True) -> dict:
    """Reject incomplete, stale or non-conducted plans before proposing a run.

    This is an engineering gate only. A JSON assertion cannot establish how the
    user has actually wired the board; the physical path must also be checked.
    """
    _mapping(plan, "plan")
    _mapping(waveform, "waveform")
    _mapping(current_tx, "current_tx")
    _digest(package_sha256, "package_sha256")
    if plan.get("schema") != "rfsig.conducted_tx_review.v1":
        raise ValueError("Unsupported link review schema")
    if plan.get("connection") != "conducted_50ohm_no_antenna":
        raise ValueError("Only a reviewed 50-ohm conducted path is supported")
    if plan.get("package_sha256") != package_sha256:
        raise ValueError("Review is not bound to this waveform package")
    if _digest(plan.get("waveform_sha256"), "waveform_sha256") != waveform.get("raw_sha256"):
        raise ValueError("Review is not bound to this waveform")
    if plan.get("waveform_name") != waveform.get("name"):
        raise ValueError("Waveform name mismatch")
    for key in ("physical_connection_checked", "tx_pa_included_in_power_spec",
                "unused_tx_ports_handled_per_manual"):
        if plan.get(key) is not True:
            raise ValueError(f"Missing physical verification: {key}")
    duration = _finite(plan.get("duration_seconds"), "duration_seconds")
    if not 0 < duration <= 60:
        raise ValueError("Source sessions must be finite and at most 60 seconds")
    expected = _mapping(plan.get("expected_tx"), "expected_tx")
    for key in ("board_model", "guard_identity", "identity_kind", "sample_rate_hz", "tx_dma_sample_rate_hz", "tx_lo_hz",
                "tx_rf_bandwidth_hz", "tx_hardwaregain_db", "tx_rf_port"):
        if key not in expected or expected[key] is None or expected[key] == "":
            raise ValueError(f"Missing expected TX setting: {key}")
        if current_tx.get(key) != expected[key]:
            raise ValueError(f"Live TX setting differs from reviewed value: {key}")
    if expected["board_model"] != "PUZHI PZSDR P201":
        raise ValueError("This source entry is restricted to the original verified P201")
    for key in ("guard_identity", "tx_rf_port"):
        value = expected[key]
        if not isinstance(value, str) or not value or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError(f"{key} must be a nonempty printable identifier")
    if expected["identity_kind"] not in ("hardware_serial", "boot_session"):
        raise ValueError("A hardware serial or explicit current-boot identity is required")
    if expected["identity_kind"] == "boot_session" and re.fullmatch(
            r"boot-session:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", expected["guard_identity"]) is None:
        raise ValueError("Invalid current-boot identity; it is not a permanent hardware serial")
    for key in ("sample_rate_hz", "tx_dma_sample_rate_hz", "tx_lo_hz", "tx_rf_bandwidth_hz"):
        if type(expected[key]) is not int:
            raise ValueError(f"{key} must be an integer readback in Hz")
    fs = _finite(expected["sample_rate_hz"], "sample_rate_hz")
    if expected["tx_dma_sample_rate_hz"] != expected["sample_rate_hz"]:
        raise ValueError("TX DMA rate differs from PHY; this candidate requires interpolation bypass")
    if fs != waveform["sample_rate_hz"]:
        raise ValueError("Waveform and actual TX sampling rates differ")
    lo = _finite(expected["tx_lo_hz"], "tx_lo_hz")
    bw = _finite(expected["tx_rf_bandwidth_hz"], "tx_rf_bandwidth_hz")
    gain = _finite(expected["tx_hardwaregain_db"], "tx_hardwaregain_db")
    if not 0 < fs <= 61440000 or not 70000000 <= lo <= 6000000000 or not 0 < bw <= 56000000 or not -89.75 <= gain <= 0:
        raise ValueError("Reviewed setting is outside this source program's supported range")
    edges = waveform["baseband_support_hz"]
    if not isinstance(edges, (list, tuple)) or len(edges) != 2:
        raise ValueError("Invalid waveform frequency support")
    edges = [_finite(x, "frequency support") for x in edges]
    if edges[0] > edges[1]:
        raise ValueError("Invalid waveform frequency support")
    # The finite RRC has out-of-band sidelobes; this check only covers its ideal support.
    if bw <= 0 or fs <= 0 or max(abs(edges[0]), abs(edges[1])) >= min(fs, bw) / 2:
        raise ValueError("Waveform does not fit within current sample/RF bandwidth")
    rf_edges = [lo + edges[0], lo + edges[1]]
    components = _mapping(plan.get("components"), "components")
    for name in ("tx_connector", "rx_connector", "cable", "attenuator"):
        item = _mapping(components.get(name), name)
        if not item.get("model") or item.get("impedance_ohm") != 50:
            raise ValueError(f"Missing model or 50-ohm impedance: {name}")
        low = _finite(item.get("min_frequency_hz"), name + " min_frequency_hz")
        high = _finite(item.get("max_frequency_hz"), name + " max_frequency_hz")
        if not 0 <= low <= rf_edges[0] <= rf_edges[1] <= high:
            raise ValueError(f"Frequency coverage does not match: {name}")
    evidence = _mapping(plan.get("evidence"), "evidence")
    for name in ("tx_connector_power", "rx_connector_recommended_input", "attenuator_rating",
                 "cable_connectors", "physical_connection"):
        item = _mapping(evidence.get(name), "evidence " + name)
        filename = item.get("path")
        if not isinstance(filename, str) or not filename or not isinstance(item.get("locator"), str) or not item["locator"]:
            raise ValueError(f"Missing verifiable local evidence: {name}")
        path = Path(filename)
        _digest(item.get("sha256"), "evidence " + name)
        if not path.is_absolute():
            raise ValueError(f"Evidence path must be absolute: {name}")
        if verify_evidence and (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]):
            raise ValueError(f"Evidence missing or changed: {name}")
    budget_data = _mapping(plan.get("power_budget"), "power_budget")
    if set(budget_data) != set(ConductedLink.__dataclass_fields__):
        raise ValueError("Connector power budget is incomplete")
    budget = evaluate_conducted_link(ConductedLink(**budget_data))
    if not budget["power_budget_passed"]:
        raise ValueError("Connector power budget or attenuator rating failed")
    return {"status": "calculation_and_document_checks_passed_physical_review_required",
            "duration_seconds": duration, "rf_support_hz": rf_edges, "budget": budget,
            "identity_scope": expected["identity_kind"],
            "identity_note": "A boot-session identity expires on board reboot and must be re-read through the verified transport.",
            "rf_transmitted": False, "receiver_validated": False}
