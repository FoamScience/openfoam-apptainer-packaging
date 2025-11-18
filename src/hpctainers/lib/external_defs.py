"""External definition loading.

Handles loading additional container definitions from Git repositories
or local paths, replicating the Ansible extra_basics functionality.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ExternalDefsError(Exception):
    """Raised when external definitions loading fails."""
    pass


def is_git_url(path: str) -> bool:
    """Check if path looks like a Git URL.

    Args:
        path: Path or URL to check

    Returns:
        True if it looks like a Git URL
    """
    git_indicators = [
        'http://',
        'https://',
        'git@',
        'git://',
        '.git',
    ]
    return any(indicator in path for indicator in git_indicators)


def clone_git_repo(git_url: str, target_dir: Path) -> bool:
    """Clone a Git repository.

    Args:
        git_url: URL of Git repository
        target_dir: Where to clone to

    Returns:
        True if clone succeeded

    Raises:
        ExternalDefsError: If clone fails
    """
    try:
        logger.info(f"Cloning {git_url} to {target_dir}")

        result = subprocess.run(
            ['git', 'clone', '--depth=1', git_url, str(target_dir)],
            capture_output=True,
            text=True,
            check=True
        )

        logger.info(f"Successfully cloned {git_url}")
        return True

    except subprocess.CalledProcessError as e:
        raise ExternalDefsError(
            f"Failed to clone {git_url}: {e.stderr}"
        ) from e
    except FileNotFoundError:
        raise ExternalDefsError(
            "git command not found. Please install git."
        )


def copy_definitions(source_dir: Path, target_dir: Path) -> tuple[int, int]:
    """Copy .def files from source to target directory.

    Args:
        source_dir: Root directory of cloned repo (will look in basic/ subdirectory)
        target_dir: Destination directory (basic/)

    Returns:
        Tuple of (copied_count, skipped_count)
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    skipped_count = 0

    basic_subdir = source_dir / 'basic'
    search_dir = basic_subdir if basic_subdir.exists() else source_dir

    for def_file in search_dir.glob('*.def'):
        target_file = target_dir / def_file.name

        if target_file.exists():
            logger.debug(
                f"Definition file already exists, skipping: {def_file.name}"
            )
            skipped_count += 1
            continue

        shutil.copy2(def_file, target_file)
        logger.info(f"Copied {def_file.name} to {target_dir}")
        copied_count += 1

    return copied_count, skipped_count


def load_external_definitions(
    extra_basics_path: Optional[str | Path],
    basic_defs_dir: Path
) -> int:
    """Load external container definitions.

    Args:
        extra_basics_path: Git URL or local path to definitions
        basic_defs_dir: Target directory (basic/)

    Returns:
        Number of definition files loaded

    Raises:
        ExternalDefsError: If loading fails
    """
    if not extra_basics_path:
        return 0

    extra_basics_path = str(extra_basics_path)

    logger.info(f"Loading external definitions from: {extra_basics_path}")

    if is_git_url(extra_basics_path):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            clone_git_repo(extra_basics_path, temp_path)

            copied, skipped = copy_definitions(temp_path, basic_defs_dir)
            total = copied + skipped

            if copied > 0:
                logger.info(f"Loaded {copied} new definition(s) from Git repository")
            if skipped > 0:
                logger.info(f"Found {skipped} existing definition(s) in cache (total: {total} available)")

            return copied

    else:
        source_path = Path(extra_basics_path)

        if not source_path.exists():
            raise ExternalDefsError(
                f"External definitions path not found: {source_path}"
            )

        if not source_path.is_dir():
            raise ExternalDefsError(
                f"External definitions path is not a directory: {source_path}"
            )

        copied, skipped = copy_definitions(source_path, basic_defs_dir)
        total = copied + skipped

        if copied > 0:
            logger.info(f"Loaded {copied} new definition(s) from local path")
        if skipped > 0:
            logger.info(f"Found {skipped} existing definition(s) in cache (total: {total} available)")

        return copied
