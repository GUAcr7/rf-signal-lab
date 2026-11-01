"""Read-only allowlisted vendor TAR audit; never extracts or runs its members."""
from pathlib import Path
import tarfile
import hashlib
import json
import re
import struct
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
SOURCE = Path(r"D:\FPGA natch\plutosdr-fw.tar")
SAFE_CONFIGS = {
    "plutosdr-fw/Makefile",
    "plutosdr-fw/buildroot/.config",
    "plutosdr-fw/buildroot/configs/zynq_pzp201_defconfig",
}


def main():
    source_stat = SOURCE.stat()
    selected = []
    configs = {}
    elf_headers = {}
    exact_paths = []
    count = 0
    with tarfile.open(SOURCE, "r:") as archive:
        for member in archive:
            count += 1
            name = member.name
            if re.search(r"shadow|passwd|dropbear|private|/\.ssh/|authorized_keys", name, re.I):
                continue
            in_host = name.startswith("plutosdr-fw/buildroot/output/host/")
            tool = in_host and re.search(r"/(?:[^/]*-gcc(?:\.real)?|[^/]*-g\+\+|[^/]*-ld|toolchain-wrapper)$", name)
            sysroot = in_host and "/sysroot/" in name and re.search(r"/(?:usr/include/(?:iio|stdio|features)\.h|lib/(?:ld[^/]*\.so[^/]*|libc(?:-[0-9.]+)?\.so(?:\.[0-9]+)?))$", name)
            package = re.search(r"/(?:sysroot|toolchain)[^/]*\.(?:tar(?:\.[^/]*)?|tgz)$", name, re.I)
            if name in SAFE_CONFIGS or tool or sysroot or package:
                selected.append({"path": name, "bytes": member.size,
                                 "type": member.type.decode("ascii", "replace"),
                                 "symlink_target": member.linkname})
                if member.isfile() and (tool or sysroot):
                    handle = archive.extractfile(member)
                    prefix = handle.read(64)
                    if prefix.startswith(b"\x7fELF"):
                        bits = 32 if prefix[4] == 1 else 64
                        order = "<" if prefix[5] == 1 else ">"
                        elf_headers[name] = {
                            "elf_class_bits": bits,
                            "machine": struct.unpack_from(order + "H", prefix, 18)[0],
                            "endian": "little" if order == "<" else "big",
                            "header_hex": prefix.hex(),
                        }
                if member.isfile() and name in SAFE_CONFIGS:
                    content = archive.extractfile(member).read()
                    lines = content.decode("utf-8", "replace").splitlines()
                    kept = [line for line in lines if re.search(
                        r"^(?:BR2_(?:arm|cortex|GCC_TARGET|ARM_EABIHF|TOOLCHAIN|PACKAGE_LIBIIO|PACKAGE_PYTHON|PACKAGE_OPENBLAS)|(?:VIVADO_VERSION|TOOLCHAIN|CROSS_COMPILE|TARGET|SYSCROOT|SYSROOT))", line)]
                    configs[name] = {"sha256": hashlib.sha256(content).hexdigest(), "selected_noncredential_lines": kept}
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(SOURCE), "bytes": source_stat.st_size},
        "total_entries": count, "selected_entries": selected,
        "safe_build_configurations": configs, "selected_elf_headers": elf_headers,
        "scope": "Archive metadata, allowlisted build configuration and executable ELF headers only; no credentials, extraction or execution",
        "limitations": ["Archived Linux-host compilers cannot run as Windows executables.",
                        "A wrapper/symlink does not prove its external compiler is included.",
                        "The archived sysroot must be compared with the actual booted board before deployment."],
    }
    output = HERE / "vendor-archive-toolchain-focused.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "entries": count, "selected_entries": len(selected), "elf_headers": elf_headers}, ensure_ascii=False), flush=True)
    h = hashlib.sha256()
    with SOURCE.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    report["source"]["sha256"] = h.hexdigest()
    report["source_stat_unchanged"] = SOURCE.stat().st_size == source_stat.st_size and SOURCE.stat().st_mtime_ns == source_stat.st_mtime_ns
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_sha256": h.hexdigest(), "source_stat_unchanged": report["source_stat_unchanged"]}), flush=True)


if __name__ == "__main__":
    main()
