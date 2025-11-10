"""Configuration parser for container build system.

Parses and validates config.yaml, maintaining backward compatibility
with the Ansible-based system.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class OSConfig(BaseModel):
    """Operating system configuration."""
    distro: str
    version: str

    @field_validator('distro')
    @classmethod
    def normalize_distro(cls, v: str) -> str:
        """Convert underscores to slashes (e.g., spack_ubuntu -> spack/ubuntu)."""
        return v.replace('_', '/')

    @field_validator('version', mode='before')
    @classmethod
    def version_to_string(cls, v: Any) -> str:
        """Convert version to string (handles YAML parsing floats like 24.04)."""
        return str(v)


class MPIConfig(BaseModel):
    """MPI implementation configuration."""
    implementation: str
    version: str

    @field_validator('version', mode='before')
    @classmethod
    def version_to_string(cls, v: Any) -> str:
        """Convert version to string (handles YAML parsing floats)."""
        return str(v)


class FrameworkConfig(BaseModel):
    """Single framework configuration."""
    definition: str
    version: str
    git_ref: str = "default"

    @field_validator('version', mode='before')
    @classmethod
    def version_to_string(cls, v: Any) -> str:
        """Convert version to string (handles YAML parsing floats)."""
        return str(v)


class BasicContainerConfig(BaseModel):
    """Configuration for a basic (base) container."""
    os: OSConfig
    mpi: MPIConfig
    framework: Union[FrameworkConfig, List[FrameworkConfig]]

    @model_validator(mode='after')
    def normalize_framework(self) -> 'BasicContainerConfig':
        """Ensure framework is always a list internally."""
        if isinstance(self.framework, dict):
            self.framework = [FrameworkConfig(**self.framework)]
        elif isinstance(self.framework, FrameworkConfig):
            self.framework = [self.framework]
        return self

    def get_frameworks(self) -> List[FrameworkConfig]:
        """Get frameworks as a list."""
        if isinstance(self.framework, list):
            return self.framework
        return [self.framework]

    def is_multi_framework(self) -> bool:
        """Check if this container has multiple frameworks."""
        return len(self.get_frameworks()) > 1

    def get_mpi_container_name(self) -> str:
        """Generate MPI container name."""
        distro_clean = self.os.distro.replace('/', '-')
        return f"{distro_clean}-{self.os.version}-{self.mpi.implementation}-{self.mpi.version}"


class ProjectContainerConfig(BaseModel):
    """Configuration for a project container."""
    base_container: str
    definition: str
    build_args: Optional[Dict[str, List[str]]] = Field(default_factory=dict)


class PullConfig(BaseModel):
    """Container registry pull configuration."""
    try_to_pull: bool = True
    protocol: str = "oras"
    scope: str = "ghcr.io/foamscience"

    @field_validator('protocol')
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """Ensure protocol is valid."""
        valid_protocols = ['oras', 'docker', 'library']
        if v not in valid_protocols:
            raise ValueError(f"Protocol must be one of {valid_protocols}, got '{v}'")
        return v


class ContainersConfig(BaseModel):
    """Top-level containers configuration."""
    extra_basics: Optional[Union[str, Path]] = None
    basic: Dict[str, BasicContainerConfig] = Field(default_factory=dict)
    projects: Dict[str, ProjectContainerConfig] = Field(default_factory=dict)


class Config(BaseModel):
    """Top-level configuration."""
    containers: ContainersConfig
    pull: PullConfig = Field(default_factory=PullConfig)


class ConfigParser:
    """Parse and validate container build configuration."""

    def __init__(self, config_path: Union[str, Path]):
        """Initialize parser with config file path.

        Args:
            config_path: Path to config.yaml file
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        self.config: Optional[Config] = None
        self._raw_config: Optional[Dict[str, Any]] = None

    def parse(self) -> Config:
        """Parse and validate configuration.

        Returns:
            Validated configuration object

        Raises:
            yaml.YAMLError: If YAML parsing fails
            pydantic.ValidationError: If validation fails
        """
        with open(self.config_path) as f:
            self._raw_config = yaml.safe_load(f)

        self.config = Config(**self._raw_config)
        return self.config

    def get_unique_mpi_configs(self) -> List[tuple[str, OSConfig, MPIConfig]]:
        """Extract unique MPI configurations from basic containers.

        Returns:
            List of (container_name, os_config, mpi_config) tuples
        """
        if not self.config:
            raise ValueError("Configuration not parsed. Call parse() first.")

        mpi_configs = []
        seen = set()

        for name, basic in self.config.containers.basic.items():
            mpi_name = basic.get_mpi_container_name()
            if mpi_name not in seen:
                seen.add(mpi_name)
                mpi_configs.append((mpi_name, basic.os, basic.mpi))

        return mpi_configs

    def get_basic_containers(self) -> Dict[str, BasicContainerConfig]:
        """Get all basic container configurations.

        Returns:
            Dictionary mapping container names to configurations
        """
        if not self.config:
            raise ValueError("Configuration not parsed. Call parse() first.")
        return self.config.containers.basic

    def get_project_containers(self) -> Dict[str, ProjectContainerConfig]:
        """Get all project container configurations.

        Returns:
            Dictionary mapping project names to configurations
        """
        if not self.config:
            raise ValueError("Configuration not parsed. Call parse() first.")
        return self.config.containers.projects

    def get_pull_config(self) -> PullConfig:
        """Get pull configuration.

        Returns:
            Pull configuration object
        """
        if not self.config:
            raise ValueError("Configuration not parsed. Call parse() first.")
        return self.config.pull

    def get_extra_basics_path(self) -> Optional[str]:
        """Get path to extra basics definitions.

        Returns:
            Path/URL to extra basics directory/repo, or None if not specified
        """
        if not self.config:
            raise ValueError("Configuration not parsed. Call parse() first.")

        if self.config.containers.extra_basics:
            return str(self.config.containers.extra_basics)
        return None


def load_config(config_path: Union[str, Path]) -> ConfigParser:
    """Load and parse configuration file.

    Args:
        config_path: Path to config.yaml

    Returns:
        Parsed configuration

    Example:
        >>> parser = load_config("config.yaml")
        >>> parser.parse()
        >>> mpi_configs = parser.get_unique_mpi_configs()
    """
    parser = ConfigParser(config_path)
    parser.parse()
    return parser
