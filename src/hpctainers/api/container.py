"""Container class for fluent API.

Provides a Dagger-style fluent interface for building Apptainer containers.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class BuildStep:
    """Represents a single build step in the container pipeline."""

    step_type: str
    args: Dict[str, Any] = field(default_factory=dict)

    def to_definition(self) -> str:
        """Convert step to Apptainer definition section.

        Returns:
            Definition file content for this step
        """
        if self.step_type == "from":
            return f"Bootstrap: docker\nFrom: {self.args['base_image']}\n"

        elif self.step_type == "exec":
            cmd = self.args['cmd']
            cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
            return f"    {cmd_str}\n"

        elif self.step_type == "env":
            return f"    export {self.args['name']}={self.args['value']}\n"

        elif self.step_type == "file":
            return f"{self.args['dest']}\n"

        return ""


class ContainerImpl:
    """Implementation of Container fluent API.

    This class provides method chaining for building containers in a
    Dagger-style interface while generating Apptainer definition files.
    """

    def __init__(self, name: Optional[str] = None):
        """Initialize container.

        Args:
            name: Optional container name
        """
        self.name = name or "container"
        self.steps: List[BuildStep] = []
        self.base_image: Optional[str] = None
        self.env_vars: Dict[str, str] = {}
        self.files: Dict[str, str] = {}  # dest -> content
        self.directories: Dict[str, Path] = {}  # dest -> source
        self.post_commands: List[List[str]] = []

        self.mpi_impl: Optional[str] = None
        self.mpi_version: Optional[str] = None
        self.frameworks: List[Dict[str, str]] = []

        self.source_scripts: List[str] = []  # List of script paths to source
        self.python_envs: List[str] = []  # List of Python venv paths
        self.uv_envs: List[str] = []  # List of UV env files

    def from_(self, base_image: str) -> ContainerImpl:
        """Bootstrap container from base image.

        Args:
            base_image: Base image reference (e.g., 'ubuntu:24.04')

        Returns:
            Self for method chaining
        """
        self.base_image = base_image
        self.steps.append(BuildStep(step_type="from", args={"base_image": base_image}))
        logger.debug(f"Container from {base_image}")
        return self

    def with_exec(self, cmd: Union[List[str], str], **kwargs) -> ContainerImpl:
        """Execute command in container.

        Args:
            cmd: Command and arguments to execute
            **kwargs: Additional options (env, cwd, etc.)

        Returns:
            Self for method chaining
        """
        if isinstance(cmd, str):
            cmd = [cmd]

        self.post_commands.append(cmd)
        self.steps.append(BuildStep(step_type="exec", args={"cmd": cmd, **kwargs}))
        logger.debug(f"Container exec: {cmd}")
        return self

    def with_file(self, path: str, content: str, **kwargs) -> ContainerImpl:
        """Add file to container.

        Args:
            path: Destination path in container
            content: File content
            **kwargs: Additional options (permissions, owner, etc.)

        Returns:
            Self for method chaining
        """
        self.files[path] = content
        self.steps.append(BuildStep(
            step_type="file",
            args={"dest": path, "content": content, **kwargs}
        ))
        logger.debug(f"Container file: {path}")
        return self

    def with_directory(self, path: str, source: Union[str, Path], **kwargs) -> ContainerImpl:
        """Mount directory in container.

        Args:
            path: Destination path in container
            source: Source directory on host
            **kwargs: Additional options (exclude, etc.)

        Returns:
            Self for method chaining
        """
        self.directories[path] = Path(source)
        self.steps.append(BuildStep(
            step_type="directory",
            args={"dest": path, "source": str(source), **kwargs}
        ))
        logger.debug(f"Container directory: {path} <- {source}")
        return self

    def with_env_variable(self, name: str, value: str) -> ContainerImpl:
        """Set environment variable.

        Args:
            name: Variable name
            value: Variable value

        Returns:
            Self for method chaining
        """
        self.env_vars[name] = value
        self.steps.append(BuildStep(
            step_type="env",
            args={"name": name, "value": value}
        ))
        logger.debug(f"Container env: {name}={value}")
        return self

    def with_mpi(self, implementation: str, version: str) -> ContainerImpl:
        """Add MPI implementation to container.

        Args:
            implementation: MPI implementation (openmpi, mpich, intel-mpi)
            version: MPI version

        Returns:
            Self for method chaining
        """
        self.mpi_impl = implementation
        self.mpi_version = version
        self.steps.append(BuildStep(
            step_type="mpi",
            args={"implementation": implementation, "version": version}
        ))
        logger.debug(f"Container MPI: {implementation} {version}")
        return self

    def with_framework(
        self,
        definition: str,
        version: str,
        git_ref: str = "default"
    ) -> ContainerImpl:
        """Add HPC framework to container.

        Uses existing framework definition files from the builtin definitions
        directory. If the framework doesn't exist, you can create a template
        with: dag.create_framework_template("basic/{framework-name}.def")

        Args:
            definition: Framework definition name (e.g., "openfoam", "hpctoolkit")
            version: Framework version
            git_ref: Git reference for source builds (default: "default")

        Returns:
            Self for method chaining

        Raises:
            FileNotFoundError: If framework definition doesn't exist
        """
        from hpctainers.lib.package_data import get_builtin_definitions_dir
        basic_dir = get_builtin_definitions_dir()

        if basic_dir and basic_dir.exists():
            framework_def = basic_dir / f"{definition}.def"
            if not framework_def.exists():
                logger.warning(
                    f"Framework definition '{definition}' not found in builtin definitions.\n"
                    f"To create a template: from hpctainers.api import dag; "
                    f"dag.create_framework_template('basic/{definition}.def')\n"
                    f"Or use CLI: hpctainers --create-framework basic/{definition}.def"
                )

        self.frameworks.append({
            "definition": definition,
            "version": version,
            "git_ref": git_ref
        })
        self.steps.append(BuildStep(
            step_type="framework",
            args={"definition": definition, "version": version, "git_ref": git_ref}
        ))
        logger.debug(f"Container framework: {definition} {version}")
        return self

    def with_spack_env(self, packages: Union[List[str], str]) -> ContainerImpl:
        """Install packages using Spack package manager.

        Args:
            packages: Package(s) to install via Spack

        Returns:
            Self for method chaining
        """
        if isinstance(packages, str):
            packages = [packages]

        self.post_commands.append([
            "bash", "-c",
            "if [ ! -d /opt/spack ]; then "
            "git clone --depth=1 https://github.com/spack/spack.git /opt/spack; "
            "fi"
        ])
        self.post_commands.append([
            "bash", "-c",
            ". /opt/spack/share/spack/setup-env.sh && " +
            " && ".join([f"spack install {pkg}" for pkg in packages])
        ])

        self.steps.append(BuildStep(
            step_type="spack",
            args={"packages": packages}
        ))
        logger.debug(f"Container spack: {packages}")
        return self

    def with_build_tools(self, remove_after: bool = True) -> ContainerImpl:
        """Add build tools (gcc, g++, make, etc.) to container.

        This is useful for multi-stage builds where you compile software
        but don't need the build tools in the final image.

        Args:
            remove_after: Whether to remove build tools after use (default: True)

        Returns:
            Self for method chaining
        """
        self.post_commands.append([
            "apt-get", "update"
        ])
        self.post_commands.append([
            "apt-get", "install", "-y", "build-essential", "gfortran", "cmake"
        ])

        if remove_after:
            logger.debug("Build tools will be removed after use")

        self.steps.append(BuildStep(
            step_type="build_tools",
            args={"remove_after": remove_after}
        ))
        logger.debug(f"Container build_tools: remove_after={remove_after}")
        return self

    def with_source_script(self, script_path: str, app_name: Optional[str] = None) -> ContainerImpl:
        """Add a source script to /apps.json.

        This script will be automatically sourced in the container environment.

        Args:
            script_path: Absolute path to the script to source (e.g., "/opt/myapp/setup.sh")
            app_name: Optional app name for /apps.json entry (defaults to script basename)

        Returns:
            Self for method chaining

        Example:
            >>> container.with_source_script("/opt/myapp/setup.sh", "myapp")
        """
        if app_name is None:
            from pathlib import Path
            app_name = Path(script_path).stem

        self.source_scripts.append((app_name, script_path))
        self.steps.append(BuildStep(
            step_type="source_script",
            args={"app_name": app_name, "script_path": script_path}
        ))
        logger.debug(f"Container source_script: {app_name} -> {script_path}")
        return self

    def with_python_env(self, venv_path: str, app_name: Optional[str] = None) -> ContainerImpl:
        """Add a Python virtual environment to /apps.json.

        The venv will be automatically activated in the container environment.

        Args:
            venv_path: Absolute path to the Python venv (e.g., "/opt/myapp/venv")
            app_name: Optional app name for /apps.json entry (defaults to venv basename)

        Returns:
            Self for method chaining

        Example:
            >>> container.with_python_env("/opt/myapp/venv", "myapp")
        """
        if app_name is None:
            from pathlib import Path
            app_name = Path(venv_path).parent.name

        self.python_envs.append((app_name, venv_path))
        self.steps.append(BuildStep(
            step_type="python_env",
            args={"app_name": app_name, "venv_path": venv_path}
        ))
        logger.debug(f"Container python_env: {app_name} -> {venv_path}")
        return self

    def with_uv_env(self, env_file: str, app_name: Optional[str] = None) -> ContainerImpl:
        """Add a UV environment file to /apps.json.

        The UV env file will be automatically sourced in the container environment.

        Args:
            env_file: Absolute path to the UV environment file (e.g., "/opt/myapp/.venv/uv.env")
            app_name: Optional app name for /apps.json entry (defaults to file parent dir)

        Returns:
            Self for method chaining

        Example:
            >>> container.with_uv_env("/opt/myapp/.venv/uv.env", "myapp")
        """
        if app_name is None:
            from pathlib import Path
            app_name = Path(env_file).parent.parent.name

        self.uv_envs.append((app_name, env_file))
        self.steps.append(BuildStep(
            step_type="uv_env",
            args={"app_name": app_name, "env_file": env_file}
        ))
        logger.debug(f"Container uv_env: {app_name} -> {env_file}")
        return self

    def terminal(self, cmd: Optional[str] = None) -> ContainerImpl:
        """Open interactive terminal in container.

        This builds the container (if not already built) and opens
        an interactive shell for debugging.

        Args:
            cmd: Optional shell command to run

        Returns:
            Self for method chaining
        """
        logger.info("Opening interactive terminal...")

        sif_path = self.build()

        shell_cmd = cmd if cmd else "/bin/bash"
        subprocess.run(
            ["apptainer", "shell", str(sif_path)],
            check=False
        )

        return self

    def to_definition(self, container_type: str = "auto") -> str:
        """Generate Apptainer definition file from container specification.

        This translates the programmatic container definition into a .def file
        that matches the format of existing definitions, including proper
        bootstrapping, /apps.json handling, and environment setup.

        Args:
            container_type: Type of container ("simple", "mpi", "framework", "project", "auto")
                           "auto" automatically detects based on methods used

        Returns:
            Definition file content as string

        Example:
            >>> container = dag.container().from_("ubuntu:24.04").with_mpi("openmpi", "4.1.5")
            >>> definition = container.to_definition()
            >>> Path("basic/my-container.def").write_text(definition)
        """
        lines = []

        if container_type == "auto":
            if self.frameworks:
                container_type = "project"
            elif self.mpi_impl:
                container_type = "mpi"
            else:
                container_type = "simple"

        lines.append("# " + "-" * 75)
        lines.append("#")
        lines.append(f"# Generated container definition")
        lines.append("#")
        lines.append("# Build:")
        lines.append(f"#   apptainer build {self.name}.sif {self.name}.def")
        lines.append("#")
        lines.append("# " + "-" * 75)

        if container_type == "simple":
            lines.append("Bootstrap: docker")
            lines.append(f"From: {self.base_image}")
        elif container_type == "mpi":
            lines.append("Bootstrap: docker")
            lines.append(f"From: {self.base_image}")
        else:
            lines.append("Bootstrap: localimage")
            lines.append("From: containers/basic/{{ BASE_CONTAINER }}.sif")

        lines.append("")

        lines.append("%arguments")

        if container_type != "simple":
            if self.base_image and ":" in self.base_image:
                os_distro, os_version = self.base_image.split(":", 1)
            else:
                os_distro, os_version = "ubuntu", "24.04"

            lines.append(f"    OS_DISTRO={os_distro}")
            lines.append(f"    OS_VERSION={os_version}")

        if self.mpi_impl and container_type == "mpi":
            lines.append(f"    MPI_IMPLEMENTATION={self.mpi_impl}")
            lines.append(f"    MPI_VERSION={self.mpi_version}")

        if self.frameworks:
            fw = self.frameworks[0]
            lines.append(f"    FRAMEWORK_VERSION={fw['version']}")
            lines.append(f"    FRAMEWORK_GIT_REF={fw.get('git_ref', 'default')}")

        lines.append("")

        lines.append("%post -c /bin/bash")
        lines.append("    DEBIAN_FRONTEND=noninteractive")

        if self.env_vars:
            lines.append("")
            lines.append("    # Environment variables")
            for name, value in self.env_vars.items():
                lines.append(f"    export {name}={value}")

        if self.post_commands:
            lines.append("")
            lines.append("    # Commands")
            for cmd in self.post_commands:
                if isinstance(cmd, list):
                    cmd_str = " ".join(cmd)
                else:
                    cmd_str = cmd
                lines.append(f"    {cmd_str}")

        lines.append("")
        lines.append("    # Update /apps.json")
        if container_type == "simple":
            lines.append("    echo '{}' > /apps.json")

        metadata_entries = []

        if self.mpi_impl and container_type == "mpi":
            metadata_entries.append(f"""
    jq --arg app {self.mpi_impl} \\
        '.[$app] |= if . == null then
        {{
            "version": "{self.mpi_version}",
            "source_script": "/opt/ompi/bashrc"
        }}
        else . +
        {{
            "version": "{self.mpi_version}",
            "source_script": "/opt/ompi/bashrc"
        }} end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json""")

        if container_type == "framework":
            for fw in self.frameworks:
                fw_name = fw['definition']
                fw_version = fw['version']
                fw_ref = fw.get('git_ref', 'default')

                metadata_entries.append(f"""
    jq --arg app {fw_name} --arg commit {fw_ref} --arg branch {fw_ref} \\
        '.[$app] |= if . == null then
        {{
            "version": "{fw_version}",
            "branch": $branch,
            "commit": $commit
        }}
        else . +
        {{
            "version": "{fw_version}",
            "branch": $branch,
            "commit": $commit
        }} end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json""")

        for app_name, script_path in self.source_scripts:
            metadata_entries.append(f"""
    jq --arg app {app_name} --arg script '{script_path}' \\
        '.[$app] |= if . == null then
        {{
            "source_script": $script
        }}
        else . +
        {{
            "source_script": $script
        }} end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json""")

        for app_name, venv_path in self.python_envs:
            metadata_entries.append(f"""
    jq --arg app {app_name} --arg venv '{venv_path}' \\
        '.[$app] |= if . == null then
        {{
            "python_env": $venv
        }}
        else . +
        {{
            "python_env": $venv
        }} end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json""")

        for app_name, env_file in self.uv_envs:
            metadata_entries.append(f"""
    jq --arg app {app_name} --arg uvenv '{env_file}' \\
        '.[$app] |= if . == null then
        {{
            "uv_env": $uvenv
        }}
        else . +
        {{
            "uv_env": $uvenv
        }} end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json""")

        for entry in metadata_entries:
            lines.append(entry)

        lines.append("")

        if container_type == "mpi":
            lines.append("%environment")
            lines.append("    #!/bin/bash")
            lines.append("    # Source scripts from /apps.json")
            lines.append("    jq -r '.. | .source_script? // empty' /apps.json | while read -r script; do")
            lines.append("      if [[ -f \"$script\" ]]; then")
            lines.append("        source \"$script\"")
            lines.append("      fi")
            lines.append("    done")
            lines.append("    # Activate Python virtual environments")
            lines.append("    jq -r '.. | .python_env? // empty' /apps.json | while read -r script; do")
            lines.append("      if [[ -d \"$script\" ]]; then")
            lines.append("        source \"$script/bin/activate\"")
            lines.append("      fi")
            lines.append("    done")
            lines.append("    # Source UV environment files")
            lines.append("    jq -r '.. | .uv_env? // empty' /apps.json | while read -r script; do")
            lines.append("      if [[ -f \"$script\" ]]; then")
            lines.append("        source \"$script\"")
            lines.append("      fi")
            lines.append("    done")
            lines.append("")

        lines.append("%runscript")
        lines.append("    #!/bin/bash")
        lines.append("    if [ $# -eq 0 ]; then")
        lines.append("        /bin/bash")
        lines.append("    else")
        lines.append("        /bin/bash -c \"$@\"")
        lines.append("    fi")
        lines.append("")

        lines.append("%labels")
        lines.append(f"    Description {self.name}")
        lines.append("    AppsFile /apps.json")
        lines.append("")

        return "\n".join(lines)

    def save_definition(self, output_path: Union[str, Path]) -> Path:
        """Save container definition to a .def file.

        Args:
            output_path: Path where definition should be saved

        Returns:
            Path to saved definition file

        Example:
            >>> container = dag.container().from_("ubuntu:24.04").with_mpi("openmpi", "4.1.5")
            >>> container.save_definition("basic/my-mpi.def")
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        definition = self.to_definition()
        output.write_text(definition)

        logger.info(f"Definition saved to: {output}")
        return output

    def build(self, output: Optional[Path] = None, name: Optional[str] = None) -> Path:
        """Build container and return path to .sif file.

        This method uses the existing BuildCache and ContainerBuilder
        infrastructure for proper caching and build orchestration.

        Args:
            output: Optional output path for .sif file (takes precedence over name)
            name: Optional name for the output .sif file (without extension or directory)
                  e.g., "my-container" → will create in appropriate directory

        Returns:
            Path to built container

        Examples:
            >>> # Use default naming based on container type
            >>> container.build()

            >>> # Specify custom name (extension added automatically)
            >>> container.build(name="my-custom-name")

            >>> # Specify full output path
            >>> container.build(output=Path("containers/custom/location.sif"))
        """
        if not self.base_image:
            raise ValueError("Container must have a base image (use .from_())")
        from hpctainers.api.builder import get_builder
        builder = get_builder()
        os_distro, os_version = self._parse_base_image()
        if output is None:
            if self.frameworks:
                container_name = name if name else self.name
                output = Path(f"containers/projects/{container_name}.sif")
            elif self.mpi_impl:
                if name:
                    output = Path(f"containers/basic/{name}.sif")
                else:
                    mpi_container_name = f"{os_distro}-{os_version}-{self.mpi_impl}-{self.mpi_version}".replace('/', '-')
                    output = Path(f"containers/basic/{mpi_container_name}.sif")
            else:
                container_name = name if name else self.name
                output = Path(f"containers/api/{container_name}.sif")
        output.parent.mkdir(parents=True, exist_ok=True)

        if self.mpi_impl and self.frameworks:
            logger.info(f"Building project container: {self.name}")
            # Step 1: Build MPI container in containers/basic/
            mpi_container_name = f"{os_distro}-{os_version}-{self.mpi_impl}-{self.mpi_version}".replace('/', '-')
            logger.info(f"  Step 1/3: Ensuring MPI container: {mpi_container_name}")
            builder.build_mpi_container(
                container_name=mpi_container_name,
                os_distro=os_distro,
                os_version=os_version,
                mpi_impl=self.mpi_impl,
                mpi_version=self.mpi_version
            )
            # Step 2: Build framework container in containers/basic/
            framework = self.frameworks[0]  # Use first framework
            framework_container_name = f"{mpi_container_name}-{framework['definition']}-{framework['version']}".replace('/', '-')
            logger.info(f"  Step 2/3: Ensuring framework container: {framework_container_name}")
            builder.build_framework_container(
                container_name=framework_container_name,
                base_container_name=mpi_container_name,
                os_distro=os_distro,
                os_version=os_version,
                mpi_impl=self.mpi_impl,
                mpi_version=self.mpi_version,
                frameworks=self.frameworks
            )
            # Step 3: Build project container in containers/projects/
            logger.info(f"  Step 3/3: Building project container: {self.name}")
            # Generate project definition
            definition_content = self.to_definition()
            def_file = Path(f"projects/{self.name}.def")
            def_file.parent.mkdir(parents=True, exist_ok=True)
            def_file.write_text(definition_content)
            logger.info(f"  Generated definition: {def_file}")
            # Build using apptainer
            build_args = {
                "BASE_CONTAINER": framework_container_name,
                "OS_DISTRO": os_distro,
                "OS_VERSION": os_version,
                "MPI_IMPLEMENTATION": self.mpi_impl,
                "MPI_VERSION": self.mpi_version,
                "FRAMEWORK_VERSION": framework['version'],
                "FRAMEWORK_GIT_REF": framework.get('git_ref', 'default')
            }
            success = builder.builder._run_apptainer_build(
                output_file=output,
                definition_file=def_file,
                build_args=build_args,
                log_file=Path(f"containers/projects/{self.name}.log"),
                force=True
            )
            if not success:
                raise RuntimeError(f"Project container build failed for {self.name}")
            return output
        elif self.mpi_impl and not self.frameworks:
            # MPI-only container - build in containers/basic/
            logger.info(f"Building MPI container: {self.name}")
            mpi_container_name = f"{os_distro}-{os_version}-{self.mpi_impl}-{self.mpi_version}".replace('/', '-')
            return builder.build_mpi_container(
                container_name=mpi_container_name,
                os_distro=os_distro,
                os_version=os_version,
                mpi_impl=self.mpi_impl,
                mpi_version=self.mpi_version
            )
        else:
            logger.info(f"Building container: {self.name}")
            return builder.build_from_base_image(
                container_name=self.name,
                base_image=self.base_image,
                post_commands=self.post_commands,
                env_vars=self.env_vars,
                output=output
            )

    def _parse_base_image(self) -> tuple[str, str]:
        """Parse base image to extract OS distro and version.

        Returns:
            Tuple of (distro, version)
        """
        # Simple parsing - assumes format like ubuntu:24.04
        if ':' in self.base_image:
            distro, version = self.base_image.split(':', 1)
            return distro, version
        else:
            return self.base_image, "latest"

    def _generate_definition(self) -> str:
        """Generate Apptainer definition file content.

        Returns:
            Definition file content
        """
        lines = []

        lines.append(f"Bootstrap: docker")
        lines.append(f"From: {self.base_image}")
        lines.append("")
        if self.files:
            lines.append("%files")
            for dest, content in self.files.items():
                lines.append(f"    # {dest}")
            lines.append("")

        if self.post_commands or self.env_vars or self.mpi_impl or self.frameworks:
            lines.append("%post")

            for name, value in self.env_vars.items():
                lines.append(f"    export {name}={value}")

            if self.env_vars:
                lines.append("")

            for cmd in self.post_commands:
                cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
                lines.append(f"    {cmd_str}")

            if self.mpi_impl:
                lines.append(f"    # Install {self.mpi_impl} {self.mpi_version}")
                lines.append(f"    # TODO: MPI installation logic")

            for framework in self.frameworks:
                lines.append(f"    # Install {framework['definition']} {framework['version']}")
                lines.append(f"    # TODO: Framework installation logic")

            lines.append("")

        return '\n'.join(lines)

    def __repr__(self) -> str:
        """String representation."""
        return f"Container(name='{self.name}', steps={len(self.steps)})"
