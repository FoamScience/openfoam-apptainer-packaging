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


def get_builtin_partials_dir() -> Path:
    """Get path to built-in partial files.

    Returns:
        Path to the partials/ directory
    """
    package = files('hpctainers')
    partials_dir = package / 'data' / 'partials'
    if hasattr(partials_dir, '__fspath__'):
        return Path(partials_dir)
    else:
        return Path(str(partials_dir))


def get_builtin_partial_file(name: str) -> Path:
    """Get path to a specific built-in partial file.

    Args:
        name: Partial file name (e.g., 'info')

    Returns:
        Path to the partial file

    Raises:
        FileNotFoundError: If the partial file doesn't exist
    """
    partials_dir = get_builtin_partials_dir()
    partial_file = partials_dir / name

    if not partial_file.exists():
        raise FileNotFoundError(
            f"Built-in partial '{name}' not found in {partials_dir}"
        )

    return partial_file


def list_builtin_partials() -> list[str]:
    """List all available built-in partial files.

    Returns:
        List of partial file names
    """
    partials_dir = get_builtin_partials_dir()

    try:
        return sorted([f.name for f in partials_dir.glob("*") if f.is_file()])
    except Exception:
        return []


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
