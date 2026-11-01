"""Load the project's chosen Windows libiio DLL without changing system settings."""

import os
import math
import re
from contextlib import contextmanager
from ctypes.util import find_library
from pathlib import Path
from typing import Iterator


def parse_iio_gain_db(value: str) -> float:
    """Parse this driver's numeric gain or numeric-plus-dB representation.

    AD9361 exposes values such as '-10.000000 dB'. Unknown units and arbitrary
    suffixes must not be stripped into apparently valid radio settings.
    """
    if not isinstance(value, str):
        raise ValueError("IIO hardwaregain must be a string")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:[ \t]+dB)?", value.strip())
    if match is None:
        raise ValueError("Expected a numeric hardwaregain with optional dB unit")
    result = float(match.group(1))
    if not math.isfinite(result):
        raise ValueError("IIO hardwaregain must be finite")
    return result


@contextmanager
def use_libiio(dll_directory: str | Path) -> Iterator[Path]:
    """Make one explicit libiio.dll available within this Python process."""
    if os.name != "nt":
        raise OSError("This libiio DLL helper is for Windows only")

    directory = Path(dll_directory).expanduser().resolve()
    dll = directory / "libiio.dll"
    if not dll.is_file():
        raise FileNotFoundError(f"libiio.dll not found in {directory}")

    previous_path = os.environ.get("PATH")
    os.environ["PATH"] = str(directory) + os.pathsep + (previous_path or "")
    try:
        with os.add_dll_directory(str(directory)):
            selected = find_library("libiio.dll")
            if selected is None or Path(selected).resolve() != dll:
                raise RuntimeError(
                    f"Expected {dll}, but Windows found {selected!r}"
                )
            yield dll
    finally:
        if previous_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = previous_path
