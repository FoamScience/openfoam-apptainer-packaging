"""Bridge between API and existing build infrastructure.

Integrates the fluent API with BuildCache and ContainerBuilder.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from hpctainers.lib.cache import BuildCache
from hpctainers.lib.container_builder import ContainerBuilder
from hpctainers.lib.registry import ContainerRegistry
from hpctainers.lib.config_parser import OSConfig, MPIConfig, FrameworkConfig

logger = logging.getLogger(__name__)


class APIBuilder:
    """Builds containers from API specifications.

    This class bridges the fluent API with the existing ContainerBuilder
    infrastructure, ensuring caching, registry pulls, and proper build
    orchestration.
    """

    def __init__(
        self,
        containers_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        try_pull: bool = True,
        force_rebuild: bool = False,
        protocol: str = "oras",
        scope: str = "ghcr.io/foamscience"
    ):
        """Initialize API builder.

        Args:
            containers_dir: Directory for output containers (default: ./containers)
            cache_enabled: Whether to use build cache
            try_pull: Whether to try pulling from registry
            force_rebuild: Force rebuild containers
            protocol: Pull protocol (oras, docker, library)
            scope: Registry scope (e.g., ghcr.io/foamscience)
        """
        self.containers_dir = Path(containers_dir or "containers")
        self.original_dir = Path.cwd()

        if cache_enabled:
            cache_dir = Path.home() / ".cache" / "hpctainers"
            self.cache = BuildCache(cache_dir)
        else:
            self.cache = None

        from hpctainers.lib.config_parser import PullConfig
        pull_config = PullConfig(
            try_to_pull=try_pull,
            protocol=protocol,
            scope=scope
        )
        self.registry = ContainerRegistry(
            protocol=pull_config.protocol,
            scope=pull_config.scope,
            try_to_pull=pull_config.try_to_pull
        )

        from hpctainers.lib.package_data import get_builtin_definitions_dir
        basic_defs_dir = get_builtin_definitions_dir()

        self.builder = ContainerBuilder(
            containers_dir=self.containers_dir,
            basic_defs_dir=basic_defs_dir,
            original_dir=self.original_dir,
            registry=self.registry,
            cache=self.cache,
            force_rebuild='__ALL__' if force_rebuild else None
        )

    def build_from_base_image(
        self,
        container_name: str,
        base_image: str,
        post_commands: list[list[str]],
        env_vars: dict[str, str],
        output: Path
    ) -> Path:
        """Build simple container from base image with commands.

        Args:
            container_name: Container name
            base_image: Base Docker image
            post_commands: Commands to run in %post
            env_vars: Environment variables
            output: Output path

        Returns:
            Path to built .sif file
        """
        lines = [
            "Bootstrap: docker",
            f"From: {base_image}",
            "",
        ]

        if env_vars or post_commands:
            lines.append("%post")
            for name, value in env_vars.items():
                lines.append(f"    export {name}={value}")
            if env_vars:
                lines.append("")
            for cmd in post_commands:
                cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
                lines.append(f"    {cmd_str}")
            lines.append("")

        definition_content = '\n'.join(lines)

        def_file = self.containers_dir / f"{container_name}.def"
        def_file.parent.mkdir(parents=True, exist_ok=True)
        def_file.write_text(definition_content)

        success = self.builder._run_apptainer_build(
            output_file=output,
            definition_file=def_file,
            build_args={},
            log_file=self.containers_dir / f"{container_name}.log",
            force=True
        )

        if not success:
            raise RuntimeError(f"Build failed for {container_name}")

        return output

    def build_mpi_container(
        self,
        container_name: str,
        os_distro: str,
        os_version: str,
        mpi_impl: str,
        mpi_version: str
    ) -> Path:
        """Build MPI container using existing definitions.

        Args:
            container_name: Container name
            os_distro: OS distribution
            os_version: OS version
            mpi_impl: MPI implementation
            mpi_version: MPI version

        Returns:
            Path to built .sif file
        """
        os_config = OSConfig(distro=os_distro, version=os_version)
        mpi_config = MPIConfig(implementation=mpi_impl, version=mpi_version)

        success = self.builder.build_mpi_container(
            container_name=container_name,
            os_config=os_config,
            mpi_config=mpi_config
        )

        if not success:
            raise RuntimeError(f"MPI container build failed for {container_name}")

        output = self.builder.mpi_output_dir / f"{container_name}.sif"
        return output

    def build_framework_container(
        self,
        container_name: str,
        base_container_name: str,
        os_distro: str,
        os_version: str,
        mpi_impl: str,
        mpi_version: str,
        frameworks: list[dict[str, str]]
    ) -> Path:
        """Build framework container using existing definitions.

        Args:
            container_name: Container name
            base_container_name: Base MPI container name
            os_distro: OS distribution
            os_version: OS version
            mpi_impl: MPI implementation
            mpi_version: MPI version
            frameworks: List of framework configurations

        Returns:
            Path to built .sif file
        """
        os_config = OSConfig(distro=os_distro, version=os_version)
        mpi_config = MPIConfig(implementation=mpi_impl, version=mpi_version)

        framework_configs = [
            FrameworkConfig(**fw) for fw in frameworks
        ]

        success = self.builder.build_framework_container(
            container_name=container_name,
            base_container_name=base_container_name,
            os_config=os_config,
            mpi_config=mpi_config,
            frameworks=framework_configs
        )

        if not success:
            raise RuntimeError(f"Framework container build failed for {container_name}")

        output = self.builder.mpi_output_dir / f"{container_name}.sif"
        return output


_builder: Optional[APIBuilder] = None

def get_builder() -> APIBuilder:
    """Get or create global builder instance.

    Returns:
        API builder instance
    """
    global _builder
    if _builder is None:
        _builder = APIBuilder()
    return _builder


def reset_builder(**kwargs) -> None:
    """Reset global builder with new configuration.

    Args:
        **kwargs: Arguments to pass to APIBuilder constructor
    """
    global _builder
    _builder = APIBuilder(**kwargs)
