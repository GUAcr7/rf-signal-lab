"""Load the project's chosen Windows libiio DLL without changing system settings."""

import os
from contextlib import contextmanager
from ctypes.util import find_library
from pathlib import Path
from typing import Iterator


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
