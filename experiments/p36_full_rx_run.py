"""Explicit operator entry point: bounded RX-only full-buffer smoke on COM8.

Import and local validation never open serial. main() alone opens one no-DTR
BoardConsole handle. No RF configuration, TX, PL/overlay or startup mutations.
Full IQ stays on the board for a separately controlled chunked retrieval.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from p32_session import BoardConsole, ROOT
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload

RF_NAMES = {"ad9361-phy", "cf-ad9361-lpc", "cf-ad9361-dds-core-lpc"}
RF_EXPECTED = {
    "in_voltage_sampling_frequency": "30720000", "in_voltage_rf_bandwidth": "18000000",
    "out_altvoltage0_RX_LO_frequency": "2450000000", "in_voltage0_gain_control_mode": "manual",
    "in_voltage0_hardwaregain": "0.000000 dB", "in_voltage0_rf_port_select": "A_BALANCED",
}
CRITICAL_KERNEL = r"Internal error:|Kernel panic|Oops:|BUG:|Unable to handle kernel"
PROCESSES = r"arm[-_]rx|arm[-_]panel|arm-tx-source|p27-rx|p33-cancel|iio_readdev|p35-(?:full|panel)-[0-9TZ]+(?:/a)?(?:\s|$)"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def boot_id(value):
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise argparse.ArgumentTypeError("expected a lowercase UUID boot ID")
    return value


def exact(record, values):
    for key, expected in values.items():
        if key not in record or type(record[key]) is not type(expected) or record[key] != expected:
            raise ValueError("unexpected field: " + key)


def load_build(path):
    """Pure local provenance gate, with all build inputs pinned before serial."""
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to((ROOT / "results").resolve()) or path.name != "report.json":
        raise ValueError("build report must be a local results/report.json")
    data = path.read_bytes()
    build = json.loads(data)
    exact(build, {"schema": "rfsig.full_rx_build.v1", "status": "offline_mock_tests_and_cross_compile_verified",
                  "runtime_libiio_required": "0.20", "default_blocks": 16, "maximum_blocks": 64,
                  "frames_per_buffer": 65536, "frame_bytes": 4, "RF_attributes_written": False,
                  "TX_API_loaded": False, "board_execution": "not_attempted", "lossless_proven": False,
                  "host_tests_have_no_failures_errors_or_skips": True})
    if type(build.get("host_test_count")) is not int or build["host_test_count"] < 25:
        raise ValueError("missing actual C test evidence")
    checks = build.get("target_checks", {})
    names = {"ELF32", "little_endian", "ARM", "hard_float_calling_convention", "armhf_interpreter",
             "pthread_linked", "required_glibc_not_newer_than_receiver", "inputs_unchanged_during_build"}
    if not names <= checks.keys() or any(checks[key] is not True for key in names):
        raise ValueError("unaccepted ELF/input checks")
    inputs = build.get("inputs_sha256", {})
    if not inputs:
        raise ValueError("build inputs are not pinned")
    for relative, digest in inputs.items():
        source = (ROOT / relative).resolve(strict=True)
        if not source.is_relative_to(ROOT.resolve()) or not re.fullmatch(r"[0-9a-f]{64}", digest) or sha(source.read_bytes()) != digest:
            raise ValueError("build input changed: " + relative)
    source = (ROOT / "embedded/arm_rx_full_p36/arm_rx_full_p36.c").resolve()
    if Path(build["source"]).resolve() != source or sha(source.read_bytes()) != build["source_sha256"]:
        raise ValueError("recorder source changed")
    binary_path = Path(build["binary"]).resolve(strict=True)
    if binary_path != (path.parent / "arm-rx-full-p36").resolve():
        raise ValueError("binary is not from this build directory")
    binary = binary_path.read_bytes()
    if len(binary) != build["binary_bytes"] or not 0 < len(binary) < 1024 * 1024 or sha(binary) != build["binary_sha256"]:
        raise ValueError("binary bytes/hash changed")
    return dict(path=path, report=build, report_bytes=data, report_sha256=sha(data), binary=binary,
                source_bytes=source.read_bytes())


def json_rows(output):
    return [json.loads(line.rstrip("\r")) for line in output.splitlines() if line.startswith("{")]


def validate_completion(output, blocks):
    rows = json_rows(output)
    starts = [row for row in rows if row.get("schema") == "rfsig.full_rx_start.v1"]
    ends = [row for row in rows if row.get("schema") == "rfsig.full_rx_completion.v1"]
    if len(starts) != 1 or len(ends) != 1 or len(rows) != 2:
        raise ValueError("missing/duplicate/unrecognized native records")
    exact(starts[0], {"requested_blocks": blocks, "frames_per_buffer": 65536, "frame_bytes": 4,
                      "allocated_iq_bytes": blocks * 262144, "RF_attributes_written": False,
                      "TX_API_loaded": False, "lossless_proven": False})
    exact(ends[0], {"status": "pass", "reason": "complete", "exit_status": 0,
                    "completed_blocks": blocks, "raw_file_bytes_written": blocks * 262144,
                    "rf_after_matches": True, "buffer_released": True, "context_released": True,
                    "cleanup_unconfirmed": False, "RF_attributes_written": False,
                    "TX_API_loaded": False, "lossless_proven": False})
    return starts[0], ends[0]


def validate_metadata(meta, blocks):
    exact(meta, {"schema": "rfsig.full_returned_buffers.v1", "status": "pass", "reason": "complete",
                 "requested_blocks": blocks, "attempted_refills": blocks, "completed_blocks": blocks,
                 "frames_per_buffer": 65536, "frame_bytes": 4, "channels": ["voltage0:I", "voltage1:Q"],
                 "source_format": "le:S12/16>>0", "storage": "original_packed_bytes_high4_undefined",
                 "sample_rate_hz": 30720000, "raw_expected_bytes": blocks * 262144,
                 "raw_file_bytes_written": blocks * 262144, "raw_file_complete": True,
                 "complete_returned_buffers_saved": True, "requested_capture_complete": True,
                 "complete_stream_saved": False, "lossless_proven": False, "known_target_proven": False,
                 "hardware_gaps": "unknown", "adc_first_sample_counter": None,
                 "timestamp_clock": "CLOCK_MONOTONIC_software_only", "libiio_major": 0, "libiio_minor": 20,
                 "RF_attributes_written": False, "TX_API_loaded": False, "rf_before_valid": True,
                 "rf_after_matches": True, "kernel_queue_count_modified": False, "kernel_queue_count": None,
                 "buffer_created": True, "buffer_released": True, "context_created": True,
                 "context_released": True, "scan_cache_disabled": True,
                 "hardware_scan_state_requires_host_readback": True, "cleanup_unconfirmed": False,
                 "cancel_requested": False, "signal_requested_stop": False, "worker_joined": True,
                 "scan_layout_validated": True, "declared_layout_and_rf_are_expectations_until_validated": True})
    stamps = meta.get("timestamps")
    if not isinstance(stamps, list) or len(stamps) != blocks:
        raise ValueError("missing block timing/byte evidence")
    previous = 0.0
    for index, stamp in enumerate(stamps):
        exact(stamp, {"block_index": index, "file_byte_offset": index * 262144,
                      "refill_bytes": 262144, "copy_complete": True})
        times = [stamp.get(key) for key in ["refill_start_s", "refill_end_s", "copy_end_s"]]
        if any(type(t) not in (int, float) or not math.isfinite(t) for t in times) or not previous <= times[0] <= times[1] <= times[2]:
            raise ValueError("invalid/unsorted software timestamps")
        previous = times[-1]
    duration = meta.get("acquisition_s")
    if type(duration) not in (int, float) or not math.isfinite(duration) or not previous <= duration <= 20:
        raise ValueError("invalid acquisition duration")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-boot", type=boot_id, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=16, choices=range(1, 65))
    args = parser.parse_args()
    inputs = load_build(args.build_report)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / ("p36-full-rx-board-" + stamp)
    out.mkdir(exist_ok=False)
    remote = "/tmp/p35-full-" + stamp[9:15]
    directory = "/tmp/p36-full-" + stamp[9:15]
    record = dict(schema="rfsig.p36_full_rx_board.v1", status="preflight", stages=[],
                  expected_boot=args.expected_boot, build_report=str(inputs["path"]),
                  build_report_sha256=inputs["report_sha256"], binary_sha256=inputs["report"]["binary_sha256"],
                  requested_blocks=args.blocks, remote_binary=remote, output_directory=directory,
                  RF_attributes_written=False, TX_operations=False, PL_or_overlay_changes=False,
                  startup_files_written=False, complete_stream_saved=False, lossless_proven=False,
                  hardware_gaps="unknown", large_IQ_transferred_to_host=False,
                  scope="finite full returned-buffer retention; running PL provenance belongs to the parent trial report")
    for name, data in [("executed.py", Path(__file__).read_bytes()), ("build-report.json", inputs["report_bytes"]),
                       ("source.c", inputs["source_bytes"]), ("arm-rx-full-p36", inputs["binary"])]:
        (out / name).write_bytes(data)

    def save():
        (out / "report.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def digest(path):
        board.command("f=" + path)
        found = re.findall(r"^([0-9a-f]{64})\s+\S+\r?$", board.command("sha256sum $f"), re.M)
        if len(found) != 1:
            raise RuntimeError("ambiguous board file SHA")
        return found[0]

    def size(path):
        board.command("f=" + path)
        found = re.findall(r"^__BYTES__([0-9]+)__END__\r?$", board.command("echo __BYTES__$(wc -c < $f)__END__"), re.M)
        if len(found) != 1:
            raise RuntimeError("ambiguous board file size")
        return int(found[0])

    def inspect(label):
        boot = board.value("/proc/sys/kernel/random/boot_id")
        taint = board.value("/proc/sys/kernel/tainted")
        if boot != args.expected_boot or taint != "0":
            raise RuntimeError("boot/taint changed or unaccepted")
        if "Zynq-Tronlong" not in board.command("uname -a"):
            raise RuntimeError("wrong receiver identity")
        processes = board.command("ps -ef")
        if re.search(PROCESSES, processes):
            raise RuntimeError("competing experiment process")
        if board.value("/sys/class/fpga_manager/fpga0/state") != "operating":
            raise RuntimeError("fabric not operating")
        board.command("p=/sys/bus/iio/devices")
        text = board.command("for d in $p/iio:device*; do echo $d; cat $d/name; done")
        pairs = re.findall(r"(/sys/bus/iio/devices/iio:device[0-9]+)\r?\n([^\r\n]+)", text)
        if any(sum(n == name for _, n in pairs) != 1 for name in RF_NAMES):
            raise RuntimeError("missing/duplicate RF devices")
        names = {name: path for path, name in pairs}
        board.command("cd " + names["ad9361-phy"])
        attributes = {key: board.value(key) for key in RF_EXPECTED}
        if attributes != RF_EXPECTED:
            raise RuntimeError("fixed RX configuration mismatch")
        board.command("cd " + names["cf-ad9361-lpc"])
        buffer = board.value("buffer/enable")
        scans = [board.value("scan_elements/in_voltage" + str(i) + "_en") for i in range(4)]
        if buffer != "0" or scans != ["0"] * 4:
            raise RuntimeError("RX is not independently idle")
        board.command("/etc/rcS.d/S99board --check-rf")
        kernel = board.command("dmesg | tail -n 160")
        if re.search(CRITICAL_KERNEL, kernel):
            raise RuntimeError("critical kernel error observed")
        result = dict(boot_id=boot, tainted=taint, attributes=attributes, buffer_enable=buffer,
                      scan_enable=scans, RF_names=names, processes=processes, dmesg=kernel)
        record[label] = result
        save()
        return result

    board = None
    native_started = False
    native_returned = False
    shell_confirmed = False
    save()
    try:
        board = BoardConsole("COM8", record, save)
        board.port = AuditPort(board.port, out)
        board.shell()
        board.port.write(b"stty echo\r")
        record["stages"].append(dict(stage="restore_tty_echo", output=board.read(.4)))
        shell_confirmed = True
        inspect("before")
        # Validate the installed timeout syntax without touching RF. The native
        # acquisition limit is 15 s; this is an outer TERM/KILL bound of 30 s.
        board.command("timeout -k 1 1 true")
        board.command("command -v gzip sha256sum wc")
        memory = board.command("cat /proc/meminfo")
        available = re.findall(r"^MemAvailable:\s+([0-9]+) kB\r?$", memory, re.M)
        if len(available) != 1 or int(available[0]) * 1024 < 2 * args.blocks * 262144 + 16 * 1024 * 1024:
            raise RuntimeError("insufficient/unknown available memory for full capture plus tmpfs")
        record["MemAvailable_kib_before"] = int(available[0])
        board.command("test ! -e " + directory)
        upload(board, remote, inputs["binary"])
        if digest(remote) != inputs["report"]["binary_sha256"]:
            raise RuntimeError("uploaded binary differs from reviewed build")
        board.command("chmod 755 " + remote)
        board.command("p=" + remote)
        board.command("o=" + directory)
        if load_build(args.build_report)["report_sha256"] != inputs["report_sha256"]:
            raise RuntimeError("host build evidence changed during preflight")
        record["status"] = "finite_capture_intent"
        record["native_capture_attempts"] = 1
        save()
        command = "timeout -k 2 28 $p $o " + str(args.blocks)
        native_started = True
        shell_confirmed = False
        try:
            output = board.command(command, timeout=40)
            native_returned = shell_confirmed = True
        except Exception:
            stage = record["stages"][-1] if record["stages"] else {}
            # A framed nonzero status still proves the shell returned. Missing
            # framing does not permit blindly feeding commands to a live task.
            if stage.get("command") == command and type(stage.get("exit_code")) is int:
                native_returned = shell_confirmed = True
                (out / "program.txt").write_text(stage.get("output", ""), encoding="utf-8")
            raise
        (out / "program.txt").write_text(output, encoding="utf-8")
        start, completion = validate_completion(output, args.blocks)
        record["native_start"], record["native_completion"] = start, completion
        board.command("cd " + directory)
        metadata_text = board.command("cat metadata.json", timeout=15)
        rows = json_rows(metadata_text)
        if len(rows) != 1:
            raise RuntimeError("ambiguous metadata JSON")
        record["native_metadata"] = validate_metadata(rows[0], args.blocks)
        (out / "metadata.json").write_text(json.dumps(rows[0], indent=2) + "\n", encoding="utf-8")
        record["native_RF_text"] = board.command("cat before.txt after.txt")
        record["status"] = "native_pass_pending_independent_state"
        save()
        after = inspect("after_capture")
        if any(after[key] != record["before"][key] for key in ["boot_id", "tainted", "attributes", "buffer_enable", "scan_enable", "RF_names"]):
            raise RuntimeError("independent state changed after full capture")
        raw = directory + "/iq-packed.bin"
        record["raw_sha256"] = digest(raw)
        record["raw_bytes"] = size(raw)
        if record["raw_bytes"] != args.blocks * 262144:
            raise RuntimeError("board raw size differs from native metadata")
        # Compression begins only after native release AND independent idle
        # checks. No large capture bytes are transferred by this runner.
        board.command("o=" + directory)
        board.command("test ! -e $o/iq-packed.bin.gz")
        board.command("timeout -k 2 28 gzip -c $o/iq-packed.bin > $o/iq-packed.bin.gz", timeout=40)
        board.command("gzip -t $o/iq-packed.bin.gz", timeout=30)
        compressed = raw + ".gz"
        record["archive_sha256"] = digest(compressed)
        record["archive_bytes"] = size(compressed)
        if record["archive_bytes"] <= 0:
            raise RuntimeError("empty gzip archive")
        if digest(raw) != record["raw_sha256"] or size(raw) != record["raw_bytes"]:
            raise RuntimeError("original raw changed during archiving")
        record["archive_board_path"] = compressed
        record["host_full_raw_verified"] = False
        record["status"] = "pass_pending_final_state"
    except Exception as exc:
        record.update(status="failed_or_unconfirmed", error=repr(exc))
    finally:
        if board:
            if shell_confirmed:
                try:
                    final = inspect("final")
                    record["independent_final_idle_verified"] = True
                    if record["status"] == "pass_pending_final_state":
                        if any(final[key] != record["before"][key] for key in ["boot_id", "tainted", "attributes", "buffer_enable", "scan_enable", "RF_names"]):
                            raise RuntimeError("independent state changed before final release")
                        record["status"] = "passed_finite_full_returned_buffers_board_only_pending_host_retrieval"
                except Exception as exc:
                    record.update(status="failed_or_cleanup_unconfirmed", postcheck_error=repr(exc))
            else:
                record["cleanup_unconfirmed"] = native_started and not native_returned
            try:
                board.close()
                record["serial_closed"] = True
            except Exception as exc:
                record.update(serial_closed=False, close_error=repr(exc), status="failed_or_cleanup_unconfirmed")
        else:
            record["serial_closed"] = True
        record["native_started"], record["native_returned"] = native_started, native_returned
        record["ended_utc"] = datetime.now(timezone.utc).isoformat()
        save()
    print(out, flush=True)
    print(record["status"], flush=True)
    return 0 if record["status"].startswith("passed_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
