"""hpcTainers - HPC Container Build System.

A Python-based container build system for HPC applications using Apptainer,
with support for OpenFOAM, MPI, and other scientific computing frameworks.

Features:
- Intelligent build caching
- Parallel build execution
- Dependency graph resolution
- Security scanning (optional)
- Container size analysis and optimization
- MPI testing and validation
"""

__version__ = "1.0.0"
__author__ = "Mohammed Elwardi Fadeli"
__license__ = "MIT"

from hpctainers.cli import main

__all__ = ["main", "__version__"]
