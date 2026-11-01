"""Inspect the provided P201 RAM filesystem; do not extract or execute it.

Only whitelisted OS/ELF files have their contents interpreted. Credential and
SSH host-key entries are excluded from the saved inventory. This is evidence
about a local firmware artifact, not a probe of the currently running board.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import zlib


ELF_NAMES = {
    "bin/busybox", "lib/ld-2.28.so", "lib/libc-2.28.so", "lib/libm-2.28.so",
    "usr/bin/iio_info", "usr/bin/iio_attr", "usr/bin/iio_readdev",
    "usr/lib/libiio.so.0.24", "usr/sbin/dropbear", "usr/sbin/iiod",
    "lib/libgcc_s.so.1", "lib/libstdc++.so.6.0.25",
}
TEXT_NAMES = {"usr/lib/os-release", "etc/fstab"}
SENSITIVE = re.compile(
    r"(^|/)(?:shadow|gshadow|passwd|group|authorized_keys|known_hosts|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|dropbear_[^/]*key[^/]*)(?:$|/)"
    r"|(^|/)\.ssh/|^etc/dropbear/|^etc/(?:wpa[^/]*|device_config|default/dropbear)$"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_newc(raw: bytes):
    pos = 0
    total = 0
    excluded = 0
    names = set()
    inventory = []
    contents = {}
    while pos + 110 <= len(raw):
        header = raw[pos:pos + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError(f"Invalid newc header at byte {pos}")
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        mode, size, name_size = fields[1], fields[6], fields[11]
        if name_size < 1 or pos + 110 + name_size > len(raw):
            raise ValueError("Truncated CPIO name")
        name_bytes = raw[pos + 110:pos + 110 + name_size]
        if not name_bytes.endswith(b"\0"):
            raise ValueError("CPIO name is not terminated")
        name = name_bytes[:-1].decode("utf-8", errors="strict").removeprefix("./")
        start = (pos + 110 + name_size + 3) & ~3
        end = start + size
        if end > len(raw):
            raise ValueError("Truncated CPIO data")
        if name == "TRAILER!!!":
            return total, excluded, inventory, contents, names
        total += 1
        names.add(name)
        if SENSITIVE.search(name):
            excluded += 1
        else:
            kind = "regular" if stat.S_ISREG(mode) else "symlink" if stat.S_ISLNK(mode) else "directory" if stat.S_ISDIR(mode) else "other"
            row = {"name": name, "bytes": size, "mode": oct(mode), "kind": kind}
            if kind == "symlink":
                row["link_target"] = raw[start:end].decode("utf-8", errors="replace")
            inventory.append(row)
            if name in ELF_NAMES | TEXT_NAMES:
                contents[name] = raw[start:end]
        pos = (end + 3) & ~3
    raise ValueError("CPIO trailer was not found")


def elf_info(data: bytes):
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] not in (1, 2):
        raise ValueError("Expected ELF32 executable/shared object")
    endian = "<" if data[5] == 1 else ">"
    elf_type, machine = struct.unpack_from(endian + "HH", data, 16)
    flags = struct.unpack_from(endian + "I", data, 36)[0]
    row = {
        "elf_class_bits": 32,
        "endian": "little" if data[5] == 1 else "big",
        "machine": machine,
        "elf_type": elf_type,
        "flags_hex": hex(flags),
        "eabi_version": (flags >> 24) & 0xFF,
        "hard_float_flag": bool(flags & 0x400),
        "bytes": len(data),
        "sha256": sha256(data),
    }
    phoff = struct.unpack_from(endian + "I", data, 28)[0]
    phsize, phcount = struct.unpack_from(endian + "HH", data, 42)
    for i in range(phcount):
        offset = phoff + i * phsize
        if offset + 32 > len(data):
            raise ValueError("Truncated ELF program header")
        ph = struct.unpack_from(endian + "8I", data, offset)
        if ph[0] == 3:
            row["interpreter"] = data[ph[1]:ph[1] + ph[4]].rstrip(b"\0").decode("utf-8")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"D:\FPGA natch\pluto\uramdisk.image.gz"))
    parser.add_argument("--uenv", type=Path, default=Path(r"D:\FPGA natch\pluto\uEnv.txt"))
    args = parser.parse_args()
    source = args.source.resolve()
    before = source.stat()
    blob = source.read_bytes()
    if blob[:4] != bytes.fromhex("27051956") or len(blob) < 64:
        raise ValueError("Not a legacy U-Boot RAM disk image")
    header = struct.unpack(">7I4B32s", blob[:64])
    payload = blob[64:]
    header_for_crc = bytearray(blob[:64])
    header_for_crc[4:8] = b"\0" * 4
    checks = {
        "uimage_header_crc32_matches": (zlib.crc32(header_for_crc) & 0xFFFFFFFF) == header[1],
        "uimage_data_crc32_matches": (zlib.crc32(payload) & 0xFFFFFFFF) == header[6],
        "uimage_payload_size_matches": len(payload) == header[3],
        "uimage_linux_arm_ramdisk_gzip": header[7:11] == (5, 2, 3, 1),
    }
    if not all(checks.values()):
        raise ValueError(f"U-Boot image check failed: {checks}")
    raw = gzip.decompress(payload)  # gzip also verifies payload CRC and length.
    total, excluded, inventory, contents, names = parse_newc(raw)
    after = source.stat()
    checks["source_stat_unchanged"] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    if not checks["source_stat_unchanged"]:
        raise ValueError("Source changed during inspection")
    elves = {name: elf_info(contents[name]) for name in sorted(ELF_NAMES) if name in contents}
    checks["selected_elfs_all_arm_32le_hardfloat"] = all(
        row["elf_class_bits"] == 32 and row["endian"] == "little" and row["machine"] == 40
        and row["eabi_version"] == 5 and row["hard_float_flag"] for row in elves.values()
    )
    text = {name: contents[name].decode("utf-8") for name in sorted(TEXT_NAMES) if name in contents}
    absent_searches = {
        "python_numpy": r"(^|/)(?:python[^/]*|numpy)(?:/|$)",
        "compilers": r"(^|/)(?:gcc|g\+\+|clang|cc)(?:$|/)",
        "cxx_gcc_shared_runtime_names": r"(^|/)(?:libstdc\+\+|libgcc_s)[^/]*$",
        "inference_framework_names": r"(?i)(^|/)[^/]*(?:onnx|tensorflow|torch|ncnn)[^/]*(?:$|/)",
    }
    search_matches = {label: sorted(n for n in names if re.search(pattern, n) and not SENSITIVE.search(n)) for label, pattern in absent_searches.items()}
    uenv = args.uenv.resolve()
    uenv_bytes = uenv.read_bytes()
    safe_uenv_lines = [line for line in uenv_bytes.decode("utf-8").splitlines() if line.startswith(("ramdisk_image=", "ramdisk_load_address=", "sdboot=", "baudrate=", "maxcpus="))]
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Local firmware artifact only; no network, serial, board access, extraction or execution of its contents",
        "source": {"path": str(source), "bytes": len(blob), "sha256": sha256(blob), "mtime_ns": before.st_mtime_ns},
        "uimage": {"payload_bytes": len(payload), "os": header[7], "architecture": header[8], "type": header[9], "compression": header[10]},
        "cpio": {"format": "newc", "uncompressed_bytes": len(raw), "total_entries": total, "sensitive_entries_omitted": excluded, "inventory_entries": len(inventory)},
        "checks": checks,
        "selected_elfs": elves,
        "safe_text_evidence": text,
        "entry_name_searches": search_matches,
        "boot_configuration": {"path": str(uenv), "sha256": sha256(uenv_bytes), "selected_noncredential_lines": safe_uenv_lines},
        "limitations": [
            "This firmware image has not been proven byte-identical to the currently booted P201 system.",
            "Archive entry-name absence is not proof of absence on the running board.",
            "An fstab JFFS2 entry is not proof of a mounted, initialized, writable or persistent live partition.",
            "No Python/C application or inference model was executed on ARM; no performance/deployment acceptance.",
            "Do not use Windows x86-64, AArch64 or bare-metal arm-none-eabi executables as ARM Linux equivalents.",
            "A matching hard-float ABI/sysroot and live libc verification are needed before deployment.",
        ],
        "references": [
            "https://www.amd.com/en/products/adaptive-socs-and-fpgas/soc/zynq-7000.html",
            "https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst",
            "https://analogdevicesinc.github.io/libiio/v0.24/libiio/index.html",
            "https://wiki.analog.com/university/tools/pluto/devs/embedded_code",
        ],
        "script_sha256": sha256(Path(__file__).read_bytes()),
    }
    out = Path(__file__).resolve().parent
    (out / "firmware-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "firmware-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(out / "firmware-report.json"), "all_checks_pass": all(checks.values()), "entries": total, "source_sha256": report["source"]["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
