"""DAG entry point for container-as-code API.

Provides the main entry point (dag) for creating containers and directories.
Similar to Dagger's dag object.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from hpctainers.api.container import ContainerImpl

logger = logging.getLogger(__name__)


class DirectoryImpl:
    """Implementation of Directory API.

    Provides operations for working with directories in container builds.
    """

    def __init__(self, path: Optional[Path] = None):
        """Initialize directory.

        Args:
            path: Optional path to existing directory
        """
        self.path = path
        self.files: dict[str, str] = {}

    def with_new_file(self, path: str, content: str) -> DirectoryImpl:
        """Add new file to directory.

        Args:
            path: File path relative to directory
            content: File content

        Returns:
            Self for method chaining
        """
        self.files[path] = content
        logger.debug(f"Directory file: {path}")
        return self

    def export(self, path: Union[str, Path]) -> None:
        """Export directory to host filesystem.

        Args:
            path: Destination path on host
        """
        export_path = Path(path)
        export_path.mkdir(parents=True, exist_ok=True)

        for file_path, content in self.files.items():
            full_path = export_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        logger.info(f"Exported directory to {export_path}")


class DAGImpl:
    """DAG (Directed Acyclic Graph) implementation.

    This is the main entry point for the container-as-code API.
    It provides factory methods for creating containers and directories.

    Example:
        >>> from hpctainers.api import dag
        >>>
        >>> container = dag.container().from_("ubuntu:24.04")
        >>> directory = dag.directory()
    """

    def __init__(self):
        """Initialize DAG."""
        self._container_counter = 0

    def container(self, name: Optional[str] = None) -> ContainerImpl:
        """Create new container.

        Args:
            name: Optional container name

        Returns:
            Empty container ready for configuration
        """
        if name is None:
            self._container_counter += 1
            name = f"container-{self._container_counter}"

        logger.debug(f"Creating container: {name}")
        return ContainerImpl(name=name)

    def directory(self, path: Optional[Union[str, Path]] = None) -> DirectoryImpl:
        """Create or reference directory.

        Args:
            path: Optional path to existing directory

        Returns:
            Directory object
        """
        dir_path = Path(path) if path else None
        logger.debug(f"Creating directory: {dir_path}")
        return DirectoryImpl(path=dir_path)

    def load_yaml(self, config_path: Union[str, Path]) -> YAMLConfigBridge:
        """Load YAML configuration and expose as API objects.

        This enables hybrid workflows where YAML configurations can be
        manipulated programmatically.

        Args:
            config_path: Path to config.yaml

        Returns:
            Configuration bridge object with API access

        Example:
            >>> config = dag.load_yaml("config.yaml")
            >>> container = config.get_basic_container("foam-ubuntu")
            >>> container.build()
        """
        from hpctainers.api.yaml_bridge import YAMLConfigBridge

        logger.debug(f"Loading YAML config: {config_path}")
        return YAMLConfigBridge(config_path)

    def create_framework_template(self, output_path: Union[str, Path]) -> Path:
        """Generate a template framework definition file.

        This uses the same template generation as `hpctainers --create-framework`.
        Framework definitions should be placed in the `basic/` directory.

        Args:
            output_path: Path where template should be written

        Returns:
            Path to created template file

        Example:
            >>> # Create new framework template
            >>> dag.create_framework_template("basic/my-framework.def")
            >>> # Edit the file, then use it:
            >>> container = dag.container().from_("ubuntu:24.04").with_mpi("openmpi", "4.1.5").with_framework("my-framework", "1.0")
        """
        from hpctainers.cli import generate_framework_template
        output = Path(output_path)
        logger.info(f"Creating framework template: {output}")
        generate_framework_template(output)
        return output

    def create_project_template(self, output_path: Union[str, Path]) -> Path:
        """Generate a template project definition file.

        This uses the same template generation as `hpctainers --create-project`.
        Project definitions typically go in the `projects/` directory.

        Args:
            output_path: Path where template should be written

        Returns:
            Path to created template file

        Example:
            >>> # Create new project template
            >>> dag.create_project_template("projects/my-app.def")
            >>> # Edit the file, then build via YAML config or direct definition file use
        """
        from hpctainers.cli import generate_project_template
        output = Path(output_path)
        logger.info(f"Creating project template: {output}")
        generate_project_template(output)
        return output

    def list_available_frameworks(self) -> list[str]:
        """List available framework definitions.

        Returns framework names that can be used with .with_framework().

        Returns:
            List of framework definition names

        Example:
            >>> frameworks = dag.list_available_frameworks()
            >>> print(frameworks)
            ['openfoam', 'com-openfoam', 'foam-extend', 'hpctoolkit', ...]
        """
        from hpctainers.lib.package_data import get_builtin_definitions_dir
        basic_dir = get_builtin_definitions_dir()

        if not basic_dir or not basic_dir.exists():
            logger.warning("No builtin definitions directory found")
            return []

        frameworks = []
        for def_file in basic_dir.glob("*.def"):
            name = def_file.stem
            if not any(name.startswith(prefix) for prefix in ['ubuntu', 'debian', 'centos', 'rocky', 'openmpi', 'mpich', 'intel']):
                frameworks.append(name)

        return sorted(frameworks)

    def list_available_mpi(self) -> list[str]:
        """List available MPI implementations.

        Returns MPI implementation names that can be used with .with_mpi().

        Returns:
            List of MPI implementation names

        Example:
            >>> mpis = dag.list_available_mpi()
            >>> print(mpis)
            ['openmpi', 'mpich', 'intel-mpi', ...]
        """
        return ['openmpi']


# Global DAG instance - this is what users should import
dag = DAGImpl()
Directory = DirectoryImpl
Container = ContainerImpl
from hpctainers.api.yaml_bridge import YAMLConfigBridge
