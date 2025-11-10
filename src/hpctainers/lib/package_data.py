"""Package data access utilities.

Provides functions to access built-in definition files and other package data.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 9):
    from importlib.resources import files
else:
    from importlib_resources import files


def get_builtin_definitions_dir() -> Path:
    """Get path to built-in definition files.

    This uses importlib.resources to locate the data/basic directory
    within the installed package, ensuring it works both in development
    and when installed via pip/uv.

    Returns:
        Path to the basic/ definitions directory
    """
    package = files('hpctainers')
    basic_dir = package / 'data' / 'basic'
    if hasattr(basic_dir, '__fspath__'):
        return Path(basic_dir)
    else:
        return Path(str(basic_dir))


def get_builtin_definition_file(name: str) -> Path:
    """Get path to a specific built-in definition file.

    Args:
        name: Definition file name (without .def extension)

    Returns:
        Path to the .def file

    Raises:
        FileNotFoundError: If the definition file doesn't exist
    """
    basic_dir = get_builtin_definitions_dir()
    def_file = basic_dir / f"{name}.def"

    if not def_file.exists():
        raise FileNotFoundError(
            f"Built-in definition '{name}.def' not found in {basic_dir}"
        )

    return def_file


def list_builtin_definitions() -> list[str]:
    """List all available built-in definition files.

    Returns:
        List of definition names (without .def extension)
    """
    basic_dir = get_builtin_definitions_dir()

    try:
        def_files = list(basic_dir.glob("*.def"))
        return sorted([f.stem for f in def_files])
    except Exception:
        return []
