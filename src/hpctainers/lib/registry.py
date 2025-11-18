"""Container registry operations.

Handles pulling containers from registries (ORAS, Docker, Library)
with fallback to local builds.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised when registry operations fail."""
    pass


class ContainerRegistry:
    """Handle container registry operations."""

    def __init__(
        self,
        protocol: str = "oras",
        scope: str = "ghcr.io/foamscience",
        try_to_pull: bool = True
    ):
        """Initialize registry handler.

        Args:
            protocol: Protocol to use (oras, docker, library)
            scope: Registry scope/namespace
            try_to_pull: Whether to attempt pulling before building
        """
        self.protocol = protocol
        self.scope = scope
        self.try_to_pull = try_to_pull

    def _build_registry_url(self, container_name: str) -> str:
        """Build registry URL for container.

        Args:
            container_name: Name of container (without .sif extension)

        Returns:
            Full registry URL
        """
        if self.protocol == "library":
            # Sylabs library format: library://scope/collection/container:tag
            return f"library://{self.scope}/{container_name}:latest"
        elif self.protocol in ["oras", "docker"]:
            # OCI registry format: protocol://registry/namespace/container:tag
            return f"{self.protocol}://{self.scope}/{container_name}:latest"
        else:
            raise ValueError(f"Unknown protocol: {self.protocol}")

    def pull_container(
        self,
        container_name: str,
        output_path: Path,
        force: bool = False
    ) -> bool:
        """Attempt to pull container from registry.

        Args:
            container_name: Name of container (without .sif extension)
            output_path: Where to save the pulled container
            force: Whether to overwrite existing container

        Returns:
            True if pull succeeded, False otherwise
        """
        if not self.try_to_pull:
            logger.debug(f"Pulling disabled, skipping {container_name}")
            return False
        if output_path.exists() and not force:
            logger.info(f"Container already exists: {output_path}")
            return True
        registry_url = self._build_registry_url(container_name)
        try:
            logger.info(f"Attempting to pull {container_name} from {registry_url}")
            cmd = [
                "apptainer", "pull",
                "--force" if force else "--disable-cache",
                str(output_path),
                registry_url
            ]
            if not force:
                cmd = [c for c in cmd if c != "--force"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.info(f"Successfully pulled {container_name}")
                return True
            else:
                logger.debug(f"Pull failed for {container_name}: {result.stderr}")
                return False
        except subprocess.SubprocessError as e:
            logger.debug(f"Pull command failed for {container_name}: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error pulling {container_name}: {e}")
            return False

    def container_exists_in_registry(self, container_name: str) -> bool:
        # NotYetImplemented
        return False

    def push_container(
        self,
        container_path: Path,
        container_name: str,
        tags: Optional[list[str]] = None
    ) -> bool:
        """Push container to registry.

        Args:
            container_path: Path to local .sif file
            container_name: Name for container in registry
            tags: Optional list of tags (default: ["latest"])

        Returns:
            True if push succeeded

        Raises:
            RegistryError: If push fails
        """
        if not container_path.exists():
            raise FileNotFoundError(f"Container not found: {container_path}")

        tags = tags or ["latest"]

        try:
            for tag in tags:
                registry_url = self._build_registry_url(container_name)
                registry_url = registry_url.rsplit(":", 1)[0] + f":{tag}"

                logger.info(f"Pushing {container_name}:{tag} to {registry_url}")

                cmd = [
                    "apptainer", "push",
                    str(container_path),
                    registry_url
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )

                logger.info(f"Successfully pushed {container_name}:{tag}")

            return True

        except subprocess.CalledProcessError as e:
            raise RegistryError(
                f"Failed to push {container_name}: {e.stderr}"
            ) from e


def try_pull_or_skip(
    registry: ContainerRegistry,
    container_name: str,
    output_path: Path
) -> tuple[bool, str]:
    """Try to pull container, returning status and reason.

    Args:
        registry: Registry handler
        container_name: Name of container
        output_path: Where to save container

    Returns:
        Tuple of (should_skip_build, reason)
        - (True, "exists"): Container already exists locally
        - (True, "pulled"): Container was successfully pulled
        - (False, "pull_failed"): Need to build (pull failed)
        - (False, "no_pull"): Need to build (pulling disabled)
    """
    if output_path.exists():
        return (True, "exists")
    if registry.try_to_pull:
        pulled = registry.pull_container(container_name, output_path)
        if pulled:
            return (True, "pulled")
        return (False, "pull_failed")

    return (False, "no_pull")
