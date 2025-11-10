"""Core container building functionality.

Handles Apptainer build commands, logging, and build orchestration.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from hpctainers.lib.cache import BuildCache
from hpctainers.lib.config_parser import OSConfig, MPIConfig, FrameworkConfig
from hpctainers.lib.registry import ContainerRegistry, try_pull_or_skip

logger = logging.getLogger(__name__)


class BuildError(Exception):
    """Raised when container build fails."""
    pass


class ContainerBuilder:
    """Handles building Apptainer containers."""

    def __init__(
        self,
        containers_dir: Path,
        basic_defs_dir: Path,
        original_dir: Path,
        registry: ContainerRegistry,
        cache: Optional[BuildCache] = None,
        force_rebuild: Optional[str | set] = None,
        external_defs_dir: Optional[Path] = None
    ):
        """Initialize container builder.

        Args:
            containers_dir: Directory for output containers
            basic_defs_dir: Directory containing basic/*.def files (built-in)
            original_dir: Original working directory (for resolving paths)
            registry: Registry handler for pulls
            cache: Optional build cache
            force_rebuild: Force rebuild - can be None, '__ALL__', or set of container names
            external_defs_dir: Optional directory for external definitions (from extra_basics)
        """
        self.containers_dir = Path(containers_dir)
        self.basic_defs_dir = Path(basic_defs_dir)
        self.external_defs_dir = Path(external_defs_dir) if external_defs_dir else None
        self.original_dir = Path(original_dir)
        self.registry = registry
        self.cache = cache
        self.force_rebuild = force_rebuild

        self.mpi_output_dir = self.containers_dir / "basic"
        self.projects_output_dir = self.containers_dir / "projects"

        self.mpi_output_dir.mkdir(parents=True, exist_ok=True)
        self.projects_output_dir.mkdir(parents=True, exist_ok=True)

    def _should_force_rebuild(self, container_name: str) -> bool:
        """Check if a specific container should be force-rebuilt.

        Args:
            container_name: Name of the container to check

        Returns:
            True if this container should be force-rebuilt
        """
        if self.force_rebuild is None:
            return False
        if self.force_rebuild == '__ALL__':
            return True
        return container_name in self.force_rebuild

    def _find_definition_file(self, name: str) -> Path:
        """Find a definition file by name, checking both built-in and external locations.

        Args:
            name: Definition file name (without .def extension)

        Returns:
            Path to the definition file

        Raises:
            FileNotFoundError: If definition file not found in either location
        """
        if self.external_defs_dir:
            external_path = self.external_defs_dir / f"{name}.def"
            if external_path.exists():
                logger.debug(f"Using external definition: {external_path}")
                return external_path

        builtin_path = self.basic_defs_dir / f"{name}.def"
        if builtin_path.exists():
            logger.debug(f"Using built-in definition: {builtin_path}")
            return builtin_path

        raise FileNotFoundError(
            f"Definition file '{name}.def' not found in built-in ({self.basic_defs_dir}) "
            f"or external ({self.external_defs_dir}) definitions"
        )

    def _run_apptainer_build(
        self,
        output_file: Path,
        definition_file: Path,
        build_args: Dict[str, str],
        log_file: Optional[Path] = None,
        force: bool = False,
        env_secrets: Optional[Dict[str, str]] = None,
        container_name: Optional[str] = None
    ) -> bool:
        """Run apptainer build command.

        Args:
            output_file: Path to output .sif file
            definition_file: Path to .def file
            build_args: Dictionary of build arguments
            log_file: Optional path to log file
            force: Whether to force rebuild
            env_secrets: Optional dictionary of environment secrets (local_name -> host_var_name)
            container_name: Optional container name for container-specific temp files

        Returns:
            True if build succeeded

        Raises:
            BuildError: If build fails
        """
        import tempfile
        import os

        temp_env_file = None
        if env_secrets:
            try:
                fd, temp_env_file = tempfile.mkstemp(suffix='.sh', prefix='hpctainers_env_')
                with os.fdopen(fd, 'w') as f:
                    f.write("#!/bin/bash\n")
                    f.write("# Environment secrets for container build\n")
                    f.write("# This file is automatically removed after build\n\n")

                    for local_name, host_var_name in env_secrets.items():
                        host_value = os.environ.get(host_var_name, '')
                        if not host_value:
                            logger.warning(f"Environment variable {host_var_name} not found in host environment")
                        f.write(f"export {host_var_name}=\"{host_value}\"\n")

                logger.debug(f"Created temp env file: {temp_env_file}")

            except Exception as e:
                logger.error(f"Failed to create temp env file: {e}")
                if temp_env_file and os.path.exists(temp_env_file):
                    os.unlink(temp_env_file)
                raise BuildError(f"Failed to create environment secrets file: {e}") from e

        try:
            cmd = ["apptainer", "build"]

            if force:
                cmd.append("--force")

            cmd.append("--warn-unused-build-args")

            if temp_env_file:
                if container_name:
                    target_path = f"/tmp/hpctainers_build_env_{container_name}.sh"
                else:
                    target_path = "/tmp/hpctainers_build_env.sh"
                cmd.extend(["--bind", f"{temp_env_file}:{target_path}"])

            for key, value in sorted(build_args.items()):
                cmd.extend(["--build-arg", f"{key}={value}"])

            cmd.append(str(output_file))
            cmd.append(str(definition_file))

            logger.debug(f"Running: {' '.join(cmd)}")

            if log_file:
                with open(log_file, 'w') as log_f:
                    result = subprocess.run(
                        cmd,
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=False,
                        cwd=self.original_dir
                    )
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=self.original_dir
                )

            if result.returncode != 0:
                error_msg = f"Build failed for {output_file.name}"
                if log_file:
                    error_msg += f" (see {log_file})"
                logger.error(error_msg)
                return False

            logger.info(f"Successfully built {output_file.name}")
            return True

        except Exception as e:
            logger.exception(f"Error running apptainer build: {e}")
            raise BuildError(f"Build command failed: {e}") from e

        finally:
            if temp_env_file and os.path.exists(temp_env_file):
                try:
                    os.unlink(temp_env_file)
                    logger.debug(f"Removed temp env file: {temp_env_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove temp env file {temp_env_file}: {e}")

    def build_mpi_container(
        self,
        container_name: str,
        os_config: OSConfig,
        mpi_config: MPIConfig
    ) -> bool:
        """Build MPI base container.

        Args:
            container_name: Name for the container
            os_config: OS configuration
            mpi_config: MPI configuration

        Returns:
            True if build succeeded or was skipped (already exists/pulled)
        """
        output_file = self.mpi_output_dir / f"{container_name}.sif"
        log_file = self.containers_dir / f"{container_name}.log"

        build_args = {
            "OS_DISTRO": os_config.distro,
            "OS_VERSION": os_config.version,
            "MPI_IMPLEMENTATION": mpi_config.implementation,
            "MPI_VERSION": mpi_config.version,
        }

        if self.cache and not self._should_force_rebuild(container_name):
            def_file = self._find_definition_file(mpi_config.implementation)
            current_hash = self.cache.compute_content_hash(def_file, build_args)
            needs_rebuild, reason = self.cache.needs_rebuild(
                container_name, current_hash, output_file
            )

            if not needs_rebuild:
                logger.info(f"Skipping {container_name}: {reason}")
                return True

        skip_build, reason = try_pull_or_skip(self.registry, container_name, output_file)
        if skip_build:
            logger.info(f"Skipping {container_name}: {reason}")
            if self.cache:
                def_file = self._find_definition_file(mpi_config.implementation)
                current_hash = self.cache.compute_content_hash(def_file, build_args)
                self.cache.update_entry(
                    container_name, current_hash, def_file, build_args, output_file
                )
            return True

        definition_file = self._find_definition_file(mpi_config.implementation)

        if not definition_file.exists():
            logger.error(f"Definition file not found: {definition_file}")
            return False

        logger.info(f"Building MPI container: {container_name}")

        success = self._run_apptainer_build(
            output_file,
            definition_file,
            build_args,
            log_file,
            force=self._should_force_rebuild(container_name)
        )

        if success and self.cache:
            current_hash = self.cache.compute_content_hash(definition_file, build_args)
            self.cache.update_entry(
                container_name, current_hash, definition_file, build_args, output_file
            )

        return success

    def build_framework_container(
        self,
        container_name: str,
        base_container_name: str,
        os_config: OSConfig,
        mpi_config: MPIConfig,
        frameworks: List[FrameworkConfig]
    ) -> bool:
        """Build framework container (can be layered).

        Args:
            container_name: Name for the output container
            base_container_name: Name of base MPI container or previous layer
            os_config: OS configuration
            mpi_config: MPI configuration
            frameworks: List of frameworks to install (builds layers if > 1)

        Returns:
            True if build succeeded
        """
        if not frameworks:
            logger.error("No frameworks specified")
            return False

        current_base = base_container_name

        for idx, framework in enumerate(frameworks):
            is_last = (idx == len(frameworks) - 1)

            if len(frameworks) > 1 and not is_last:
                layer_name = f"{container_name}-layer{idx + 1}"
            else:
                layer_name = container_name

            success = self._build_single_framework(
                layer_name,
                current_base,
                os_config,
                mpi_config,
                framework
            )

            if not success:
                return False

            current_base = layer_name

        return True

    def _build_single_framework(
        self,
        container_name: str,
        base_container_name: str,
        os_config: OSConfig,
        mpi_config: MPIConfig,
        framework: FrameworkConfig
    ) -> bool:
        """Build a single framework layer.

        Args:
            container_name: Name for this container/layer
            base_container_name: Base container to build on
            os_config: OS configuration
            mpi_config: MPI configuration
            framework: Framework configuration

        Returns:
            True if build succeeded
        """
        output_file = self.mpi_output_dir / f"{container_name}.sif"
        log_file = self.containers_dir / f"{container_name}.log"

        base_container_path = self.mpi_output_dir / f"{base_container_name}.sif"

        build_args = {
            "OS_DISTRO": os_config.distro,
            "OS_VERSION": os_config.version,
            "MPI_IMPLEMENTATION": mpi_config.implementation,
            "MPI_VERSION": mpi_config.version,
            "FRAMEWORK_VERSION": framework.version,
            "FRAMEWORK_GIT_REF": framework.git_ref,
            "BASE_CONTAINER": base_container_name,
        }

        if self.cache and not self._should_force_rebuild(container_name):
            def_file = self._find_definition_file(framework.definition)
            base_hash = None
            if base_entry := self.cache.get_entry(base_container_name):
                base_hash = base_entry.content_hash

            current_hash = self.cache.compute_content_hash(
                def_file, build_args, base_hash
            )
            needs_rebuild, reason = self.cache.needs_rebuild(
                container_name, current_hash, output_file
            )

            if not needs_rebuild:
                logger.info(f"Skipping {container_name}: {reason}")
                return True

        skip_build, reason = try_pull_or_skip(self.registry, container_name, output_file)
        if skip_build:
            logger.info(f"Skipping {container_name}: {reason}")
            if self.cache:
                def_file = self._find_definition_file(framework.definition)
                base_hash = None
                if base_entry := self.cache.get_entry(base_container_name):
                    base_hash = base_entry.content_hash
                current_hash = self.cache.compute_content_hash(
                    def_file, build_args, base_hash
                )
                self.cache.update_entry(
                    container_name, current_hash, def_file, build_args,
                    output_file, base_hash
                )
            return True

        definition_file = self._find_definition_file(framework.definition)

        if not definition_file.exists():
            logger.error(f"Definition file not found: {definition_file}")
            return False

        if not base_container_path.exists():
            logger.error(f"Base container not found: {base_container_path}")
            return False

        logger.info(f"Building framework container: {container_name}")

        success = self._run_apptainer_build(
            output_file,
            definition_file,
            build_args,
            log_file,
            force=True  # Always force for framework builds (uses --force)
        )

        if success and self.cache:
            base_hash = None
            if base_entry := self.cache.get_entry(base_container_name):
                base_hash = base_entry.content_hash
            current_hash = self.cache.compute_content_hash(
                definition_file, build_args, base_hash
            )
            self.cache.update_entry(
                container_name, current_hash, definition_file, build_args,
                output_file, base_hash
            )

        return success

    def build_project_container(
        self,
        project_name: str,
        base_container_name: str,
        definition_file: Path,
        build_args: Dict[str, str],
        os_version: str = "",
        mpi_version: str = "",
        env_secrets: Optional[Dict[str, str]] = None
    ) -> bool:
        """Build project container.

        Args:
            project_name: Name of the project container
            base_container_name: Name of base container
            definition_file: Path to project .def file
            build_args: Build arguments (already includes variant-specific args)
            os_version: OS version (for build args)
            mpi_version: MPI version (for build args)
            env_secrets: Optional environment secrets (local_name -> host_var_name)

        Returns:
            True if build succeeded
        """
        output_file = self.projects_output_dir / f"{project_name}.sif"
        log_file = self.containers_dir / f"{project_name}.log"

        all_build_args = {
            "BASE_CONTAINER": base_container_name,
            "CONTAINERS_DIR": str(self.containers_dir.absolute()),
            **build_args  # Includes variant-specific args (BRANCH, etc.)
        }

        if os_version:
            all_build_args["OS_VERSION"] = os_version
        if mpi_version:
            all_build_args["MPI_VERSION"] = mpi_version

        if self.cache and not self._should_force_rebuild(project_name):
            base_hash = None
            if base_entry := self.cache.get_entry(base_container_name):
                base_hash = base_entry.content_hash

            current_hash = self.cache.compute_content_hash(
                definition_file, all_build_args, base_hash
            )
            needs_rebuild, reason = self.cache.needs_rebuild(
                project_name, current_hash, output_file
            )

            if not needs_rebuild:
                logger.info(f"Skipping {project_name}: {reason}")
                return True

        if output_file.exists() and not self._should_force_rebuild(project_name):
            logger.info(f"Skipping {project_name}: output exists")
            return True

        if not definition_file.exists():
            logger.error(f"Definition file not found: {definition_file}")
            return False

        base_path = self.mpi_output_dir / f"{base_container_name}.sif"
        if not base_path.exists():
            logger.error(f"Base container not found: {base_path}")
            return False

        logger.info(f"Building project container: {project_name}")

        success = self._run_apptainer_build(
            output_file,
            definition_file,
            all_build_args,
            log_file,
            force=True,  # Always force for project builds
            env_secrets=env_secrets,
            container_name=project_name
        )

        if success and self.cache:
            base_hash = None
            if base_entry := self.cache.get_entry(base_container_name):
                base_hash = base_entry.content_hash
            current_hash = self.cache.compute_content_hash(
                definition_file, all_build_args, base_hash
            )
            self.cache.update_entry(
                project_name, current_hash, definition_file, all_build_args,
                output_file, base_hash
            )

        return success
