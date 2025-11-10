"""Container-as-code API for hpctainers.

This module provides a Dagger-style fluent API for building HPC containers
programmatically using Python, while maintaining full backwards compatibility
with YAML configurations.

Example:
    >>> from hpctainers.api import dag, function
    >>>
    >>> # Simple container build
    >>> container = (
    >>>     dag.container()
    >>>     .from_("ubuntu:24.04")
    >>>     .with_exec(["apt-get", "update"])
    >>>     .with_exec(["apt-get", "install", "-y", "build-essential"])
    >>>     .build()
    >>> )
    >>>
    >>> # Reusable function
    >>> @function
    >>> def openmpi_container(version: str = "4.1.5"):
    >>>     return (
    >>>         dag.container()
    >>>         .from_("ubuntu:24.04")
    >>>         .with_mpi("openmpi", version)
    >>>     )
"""

from __future__ import annotations

from hpctainers.api.builder import APIBuilder, get_builder, reset_builder
from hpctainers.api.container import ContainerImpl
from hpctainers.api.dag import DAGImpl, DirectoryImpl, dag
from hpctainers.api.decorators import function, object_type
from hpctainers.api.visualization import DAGVisualizer, visualize_dependency_graph
from hpctainers.api.yaml_bridge import (
    FunctionLoader,
    YAMLConfigBridge,
    container_to_yaml,
    load_yaml_config,
)

# Main exports
__all__ = [
    "dag",
    "function",
    "object_type",
    "Container",
    "Directory",
    "DAG",
    "APIBuilder",
    "get_builder",
    "reset_builder",
    "YAMLConfigBridge",
    "load_yaml_config",
    "container_to_yaml",
    "FunctionLoader",
    "DAGVisualizer",
    "visualize_dependency_graph",
]

# Type aliases for user code
Container = ContainerImpl
Directory = DirectoryImpl
DAG = DAGImpl
