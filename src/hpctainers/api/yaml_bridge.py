"""YAML-Python bridge for hybrid workflows.

Allows Python API to load YAML configs and vice versa.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from hpctainers.api.container import ContainerImpl
from hpctainers.api.dag import dag
from hpctainers.lib.config_parser import (
    BasicContainerConfig,
    load_config,
)

logger = logging.getLogger(__name__)


class YAMLConfigBridge:
    """Bridge between YAML configuration and Python API.

    Allows loading YAML configs and converting them to API Container objects.
    """

    def __init__(self, config_path: Union[str, Path]):
        """Initialize bridge with YAML config.

        Args:
            config_path: Path to config.yaml
        """
        self.config_path = Path(config_path)
        self.parser = load_config(self.config_path)
        self._containers_cache: Dict[str, ContainerImpl] = {}

    def get_basic_container(self, name: str) -> ContainerImpl:
        """Get a basic container configuration as API Container.

        Args:
            name: Container name from config

        Returns:
            Container object

        Raises:
            KeyError: If container not found in config
        """
        if name in self._containers_cache:
            return self._containers_cache[name]

        basic_configs = self.parser.get_basic_containers()
        if name not in basic_configs:
            raise KeyError(f"Container '{name}' not found in config")

        config = basic_configs[name]
        container = self._basic_config_to_container(config)

        self._containers_cache[name] = container
        return container

    def list_basic_containers(self) -> list[str]:
        """List all basic container names.

        Returns:
            List of container names
        """
        return list(self.parser.get_basic_containers().keys())

    def _basic_config_to_container(
        self, config: BasicContainerConfig
    ) -> ContainerImpl:
        """Convert BasicContainerConfig to Container API object.

        Args:
            config: Basic container configuration

        Returns:
            Container object
        """
        base_image = f"{config.os.distro}:{config.os.version}"
        container = dag.container().from_(base_image)

        if config.mpi:
            container = container.with_mpi(
                config.mpi.implementation,
                config.mpi.version
            )

        for framework in config.get_frameworks():
            container = container.with_framework(
                framework.definition,
                framework.version,
                framework.git_ref
            )

        return container

    def to_yaml(self, container: ContainerImpl, name: str) -> str:
        """Convert Container API object to YAML config format.

        Args:
            container: Container object
            name: Name for the container

        Returns:
            YAML configuration string
        """
        lines = [f"  {name}:"]

        if hasattr(container, 'base_image') and container.base_image:
            if ':' in container.base_image:
                distro, version = container.base_image.split(':', 1)
            else:
                distro, version = container.base_image, "latest"

            lines.append(f"    os:")
            lines.append(f"      distro: {distro}")
            lines.append(f"      version: \"{version}\"")

        if hasattr(container, 'mpi_impl') and container.mpi_impl:
            lines.append(f"    mpi:")
            lines.append(f"      implementation: {container.mpi_impl}")
            lines.append(f"      version: \"{container.mpi_version}\"")

        if hasattr(container, 'frameworks') and container.frameworks:
            if len(container.frameworks) == 1:
                fw = container.frameworks[0]
                lines.append(f"    framework:")
                lines.append(f"      definition: {fw['definition']}")
                lines.append(f"      version: \"{fw['version']}\"")
                if fw.get('git_ref') != 'default':
                    lines.append(f"      git_ref: {fw['git_ref']}")
            else:
                lines.append(f"    framework:")
                for fw in container.frameworks:
                    lines.append(f"      - definition: {fw['definition']}")
                    lines.append(f"        version: \"{fw['version']}\"")
                    if fw.get('git_ref') != 'default':
                        lines.append(f"        git_ref: {fw['git_ref']}")

        return '\n'.join(lines)


class FunctionLoader:
    """Loads and executes Python functions from YAML config.

    Supports syntax like:
        python_function: "my_module:build_container"
        args:
          base: ubuntu:24.04
    """

    @staticmethod
    def load_function(function_ref: str) -> Callable:
        """Load a Python function from module:function reference.

        Args:
            function_ref: Function reference (e.g., "my_module:my_function")

        Returns:
            Function object

        Raises:
            ValueError: If function reference is invalid
            ImportError: If module cannot be imported
            AttributeError: If function not found in module
        """
        if ':' not in function_ref:
            raise ValueError(
                f"Invalid function reference: {function_ref}. "
                "Expected format: 'module:function'"
            )

        module_name, function_name = function_ref.split(':', 1)

        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise ImportError(
                f"Failed to import module '{module_name}': {e}"
            ) from e

        try:
            func = getattr(module, function_name)
        except AttributeError as e:
            raise AttributeError(
                f"Function '{function_name}' not found in module '{module_name}'"
            ) from e

        if not callable(func):
            raise TypeError(
                f"{function_ref} is not callable"
            )

        logger.debug(f"Loaded function: {function_ref}")
        return func

    @staticmethod
    def execute_function(
        function_ref: str,
        args: Optional[Dict[str, Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Load and execute a function.

        Args:
            function_ref: Function reference (e.g., "my_module:my_function")
            args: Positional arguments as dict (arg names mapped to values)
            kwargs: Keyword arguments

        Returns:
            Function result
        """
        func = FunctionLoader.load_function(function_ref)
        args = args or {}
        kwargs = kwargs or {}
        all_kwargs = {**args, **kwargs}
        logger.debug(f"Executing {function_ref} with {all_kwargs}")
        return func(**all_kwargs)


def load_yaml_config(config_path: Union[str, Path]) -> YAMLConfigBridge:
    """Load YAML configuration and expose as API bridge.

    Args:
        config_path: Path to config.yaml

    Returns:
        YAML config bridge

    Example:
        >>> config = load_yaml_config("config.yaml")
        >>> container = config.get_basic_container("foam-ubuntu")
        >>> container.build()
    """
    return YAMLConfigBridge(config_path)


def container_to_yaml(container: ContainerImpl, name: str) -> str:
    """Convert Container API object to YAML format.

    Args:
        container: Container object
        name: Container name

    Returns:
        YAML configuration string

    Example:
        >>> container = dag.container().from_("ubuntu:24.04").with_mpi("openmpi", "4.1.5")
        >>> yaml_str = container_to_yaml(container, "my-mpi-container")
        >>> print(yaml_str)
    """
    bridge = YAMLConfigBridge.__new__(YAMLConfigBridge)
    return bridge.to_yaml(container, name)
