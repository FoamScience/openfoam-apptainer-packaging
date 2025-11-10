"""Build cache for intelligent rebuild detection.

Tracks container build metadata and content hashes to determine
when rebuilds are necessary.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a cached build entry."""

    container_name: str
    content_hash: str
    built_at: str
    definition_file: str
    build_args: Dict[str, str]
    output_file: str
    base_container_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "container_name": self.container_name,
            "content_hash": self.content_hash,
            "built_at": self.built_at,
            "definition_file": self.definition_file,
            "build_args": self.build_args,
            "output_file": self.output_file,
            "base_container_hash": self.base_container_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CacheEntry:
        """Create from dictionary."""
        return cls(**data)


class BuildCache:
    """Manage build cache for containers."""

    def __init__(self, cache_dir: Path = Path(".build-cache")):
        """Initialize build cache.

        Args:
            cache_dir: Directory to store cache metadata
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._cache: Dict[str, CacheEntry] = {}
        self._load_cache()

    def _get_cache_file(self, container_name: str) -> Path:
        """Get cache file path for container.

        Args:
            container_name: Name of container

        Returns:
            Path to cache file
        """
        return self.cache_dir / f"{container_name}.json"

    def _load_cache(self) -> None:
        """Load all cache entries from disk."""
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    entry = CacheEntry.from_dict(data)
                    self._cache[entry.container_name] = entry
            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")

    def _save_entry(self, entry: CacheEntry) -> None:
        """Save cache entry to disk.

        Args:
            entry: Cache entry to save
        """
        cache_file = self._get_cache_file(entry.container_name)
        try:
            with open(cache_file, 'w') as f:
                json.dump(entry.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache entry for {entry.container_name}: {e}")

    @staticmethod
    def compute_content_hash(
        definition_file: Path,
        build_args: Dict[str, str],
        base_container_hash: Optional[str] = None
    ) -> str:
        """Compute content hash for a build.

        Args:
            definition_file: Path to .def file
            build_args: Build arguments
            base_container_hash: Hash of base container (for layered builds)

        Returns:
            SHA256 hex digest
        """
        hasher = hashlib.sha256()

        if definition_file.exists():
            with open(definition_file, 'rb') as f:
                hasher.update(f.read())
        else:
            logger.warning(f"Definition file not found: {definition_file}")

        sorted_args = sorted(build_args.items())
        args_str = json.dumps(sorted_args, sort_keys=True)
        hasher.update(args_str.encode())

        if base_container_hash:
            hasher.update(base_container_hash.encode())

        return hasher.hexdigest()

    def get_entry(self, container_name: str) -> Optional[CacheEntry]:
        """Get cache entry for container.

        Args:
            container_name: Name of container

        Returns:
            Cache entry if exists, None otherwise
        """
        return self._cache.get(container_name)

    def needs_rebuild(
        self,
        container_name: str,
        current_hash: str,
        output_file: Path
    ) -> tuple[bool, str]:
        """Determine if container needs to be rebuilt.

        Args:
            container_name: Name of container
            current_hash: Current content hash
            output_file: Expected output file path

        Returns:
            Tuple of (needs_rebuild, reason)
        """
        if not output_file.exists():
            return (True, "output_missing")

        entry = self.get_entry(container_name)
        if not entry:
            return (True, "no_cache")

        if entry.content_hash != current_hash:
            return (True, "content_changed")

        return (False, "cache_hit")

    def update_entry(
        self,
        container_name: str,
        content_hash: str,
        definition_file: Path,
        build_args: Dict[str, str],
        output_file: Path,
        base_container_hash: Optional[str] = None
    ) -> None:
        """Update cache entry after successful build.

        Args:
            container_name: Name of container
            content_hash: Content hash of the build
            definition_file: Path to definition file
            build_args: Build arguments used
            output_file: Path to output .sif file
            base_container_hash: Hash of base container
        """
        entry = CacheEntry(
            container_name=container_name,
            content_hash=content_hash,
            built_at=datetime.now().isoformat(),
            definition_file=str(definition_file),
            build_args=build_args,
            output_file=str(output_file),
            base_container_hash=base_container_hash,
        )

        self._cache[container_name] = entry
        self._save_entry(entry)
        logger.debug(f"Updated cache for {container_name}")

    def invalidate(self, container_name: str) -> None:
        """Invalidate cache entry for container.

        Args:
            container_name: Name of container
        """
        if container_name in self._cache:
            del self._cache[container_name]

        cache_file = self._get_cache_file(container_name)
        if cache_file.exists():
            cache_file.unlink()
            logger.debug(f"Invalidated cache for {container_name}")

    def invalidate_all(self) -> None:
        """Invalidate all cache entries."""
        self._cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
        logger.info("Invalidated all cache entries")

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "total_entries": len(self._cache),
            "cache_dir": str(self.cache_dir),
            "entries": {
                name: {
                    "built_at": entry.built_at,
                    "definition": entry.definition_file,
                }
                for name, entry in self._cache.items()
            }
        }
