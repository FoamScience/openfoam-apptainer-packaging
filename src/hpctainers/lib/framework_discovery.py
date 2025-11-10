"""Framework discovery and metadata extraction.

Scans for available framework definition files and extracts their metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class FrameworkInfo:
    """Information about a framework definition."""

    name: str
    """Framework name (filename without .def)"""

    path: Path
    """Path to the .def file"""

    description: Optional[str] = None
    """Description from comments"""

    arguments: Dict[str, str] = field(default_factory=dict)
    """Default argument values from %arguments"""

    bootstrap: Optional[str] = None
    """Bootstrap method (docker, localimage, etc.)"""

    from_image: Optional[str] = None
    """From image/container"""

    is_optimized: bool = False
    """Whether this is an optimized variant"""

    source: str = "built-in"
    """Source of definition (built-in or path to extra_basics)"""


def parse_definition_file(def_path: Path, source: str = "built-in") -> FrameworkInfo:
    """Parse a definition file and extract metadata.

    Args:
        def_path: Path to .def file
        source: Source of the definition (built-in or path)

    Returns:
        FrameworkInfo with extracted metadata
    """
    name = def_path.stem
    is_optimized = "-optimized" in name or "_optimized" in name

    info = FrameworkInfo(
        name=name,
        path=def_path,
        is_optimized=is_optimized,
        source=source,
    )

    try:
        content = def_path.read_text()
        lines = content.split('\n')

        description_lines = []
        for line in lines[:20]:
            line = line.strip()
            if line.startswith('#'):
                clean_line = line.lstrip('#').strip()
                if clean_line and not all(c in '-=' for c in clean_line):
                    description_lines.append(clean_line)
            elif line and not line.startswith('#'):
                break

        if description_lines:
            info.description = ' '.join(description_lines)

        for line in lines:
            line = line.strip()
            if line.startswith('Bootstrap:'):
                info.bootstrap = line.split(':', 1)[1].strip()
            elif line.startswith('From:'):
                info.from_image = line.split(':', 1)[1].strip()

        in_arguments = False
        for line in lines:
            line = line.strip()

            if line == '%arguments':
                in_arguments = True
                continue
            elif line.startswith('%') and line != '%arguments':
                in_arguments = False
                continue

            if in_arguments and '=' in line:
                key, value = line.split('=', 1)
                info.arguments[key.strip()] = value.strip()

    except Exception:
        pass

    return info


def discover_frameworks(basic_dir: Path, extra_dirs: List[Path] = None) -> List[FrameworkInfo]:
    """Discover all available framework definitions.

    Args:
        basic_dir: Path to built-in basic/ directory
        extra_dirs: Additional directories to scan (from extra_basics)

    Returns:
        List of discovered frameworks
    """
    frameworks = []

    if basic_dir.exists():
        for def_file in sorted(basic_dir.glob("*.def")):
            if def_file.stem in ['openmpi', 'mpich', 'intelmpi']:
                continue
            frameworks.append(parse_definition_file(def_file, source="built-in"))

    if extra_dirs:
        for extra_dir in extra_dirs:
            if extra_dir.exists():
                for def_file in sorted(extra_dir.glob("*.def")):
                    if def_file.stem in ['openmpi', 'mpich', 'intelmpi']:
                        continue
                    frameworks.append(parse_definition_file(
                        def_file,
                        source=str(extra_dir)
                    ))

    return frameworks


def format_framework_list(frameworks: List[FrameworkInfo], verbose: bool = False) -> str:
    """Format frameworks for display.

    Args:
        frameworks: List of framework info
        verbose: Show detailed information

    Returns:
        Formatted string
    """
    if not frameworks:
        return "No frameworks found."

    lines = []
    lines.append("\nAvailable Frameworks:")
    lines.append("=" * 80)

    for fw in sorted(frameworks, key=lambda x: x.name):
        name_line = f"\n{fw.name}"
        if fw.is_optimized:
            name_line += " (optimized)"
        lines.append(name_line)

        if fw.description:
            desc = fw.description[:100] + "..." if len(fw.description) > 100 else fw.description
            lines.append(f"  Description: {desc}")

        if fw.source != "built-in":
            lines.append(f"  Source: {fw.source}")

        if fw.bootstrap:
            lines.append(f"  Bootstrap: {fw.bootstrap}")
            if fw.from_image:
                lines.append(f"  From: {fw.from_image}")

        if fw.arguments:
            if verbose or len(fw.arguments) <= 3:
                lines.append("  Arguments:")
                for key, value in sorted(fw.arguments.items()):
                    lines.append(f"    {key} = {value}")
            else:
                lines.append(f"  Arguments: {len(fw.arguments)} defined")

        if verbose:
            lines.append(f"  Path: {fw.path}")

    lines.append("\n" + "=" * 80)
    lines.append(f"Total: {len(frameworks)} frameworks\n")

    return '\n'.join(lines)
