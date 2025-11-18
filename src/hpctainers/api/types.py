"""Type definitions for container-as-code API.

Provides type annotations and protocol definitions for the fluent API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Union


class Container(Protocol):
    """Protocol for Container objects in the API."""

    def from_(self, base_image: str) -> Container:
        """Bootstrap container from base image.

        Args:
            base_image: Base image reference (e.g., 'ubuntu:24.04')

        Returns:
            Container with base image set
        """
        ...

    def with_exec(self, cmd: List[str], **kwargs) -> Container:
        """Execute command in container.

        Args:
            cmd: Command and arguments to execute
            **kwargs: Additional options (env, cwd, etc.)

        Returns:
            Container after command execution
        """
        ...

    def with_file(self, path: str, content: str, **kwargs) -> Container:
        """Add file to container.

        Args:
            path: Destination path in container
            content: File content
            **kwargs: Additional options (permissions, owner, etc.)

        Returns:
            Container with file added
        """
        ...

    def with_directory(self, path: str, source: Union[str, Path], **kwargs) -> Container:
        """Mount directory in container.

        Args:
            path: Destination path in container
            source: Source directory on host
            **kwargs: Additional options (exclude, etc.)

        Returns:
            Container with directory mounted
        """
        ...

    def with_env_variable(self, name: str, value: str) -> Container:
        """Set environment variable.

        Args:
            name: Variable name
            value: Variable value

        Returns:
            Container with environment variable set
        """
        ...

    def with_mpi(self, implementation: str, version: str) -> Container:
        """Add MPI implementation to container.

        Args:
            implementation: MPI implementation (openmpi, mpich, intel-mpi)
            version: MPI version

        Returns:
            Container with MPI installed
        """
        ...

    def with_framework(
        self,
        definition: str,
        version: str,
        git_ref: str = "default"
    ) -> Container:
        """Add HPC framework to container.

        Args:
            definition: Framework definition name
            version: Framework version
            git_ref: Git reference for source

        Returns:
            Container with framework installed
        """
        ...

    def build(self, output: Optional[Path] = None) -> Path:
        """Build container and return path to .sif file.

        Args:
            output: Optional output path for .sif file

        Returns:
            Path to built container
        """
        ...

    def terminal(self, cmd: Optional[str] = None) -> Container:
        """Open interactive terminal in container.

        Args:
            cmd: Optional shell command to run

        Returns:
            Container (for chaining)
        """
        ...


class Directory(Protocol):
    """Protocol for Directory objects in the API."""

    def with_new_file(self, path: str, content: str) -> Directory:
        """Add new file to directory.

        Args:
            path: File path relative to directory
            content: File content

        Returns:
            Directory with file added
        """
        ...

    def export(self, path: Union[str, Path]) -> None:
        """Export directory to host filesystem.

        Args:
            path: Destination path on host
        """
        ...


class DAG(Protocol):
    """Protocol for DAG entry point."""

    def container(self) -> Container:
        """Create new container.

        Returns:
            Empty container
        """
        ...

    def directory(self, path: Optional[Union[str, Path]] = None) -> Directory:
        """Create or reference directory.

        Args:
            path: Optional path to existing directory

        Returns:
            Directory object
        """
        ...


BuildArgs = Dict[str, str]
EnvVars = Dict[str, str]
Command = List[str]
