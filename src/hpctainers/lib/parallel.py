"""Parallel build execution.

Handles concurrent container builds while respecting dependencies.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class BuildTask:
    """Represents a single container build task."""

    container_name: str
    build_func: Callable[[], bool]
    depends_on: List[str]
    metadata: Dict[str, Any]


class BuildResult:
    """Result of a build task."""

    def __init__(
        self,
        container_name: str,
        success: bool,
        error: Optional[Exception] = None,
        skipped: bool = False,
        reason: str = ""
    ):
        """Initialize build result.

        Args:
            container_name: Name of container
            success: Whether build succeeded
            error: Exception if build failed
            skipped: Whether build was skipped
            reason: Reason for skip or failure
        """
        self.container_name = container_name
        self.success = success
        self.error = error
        self.skipped = skipped
        self.reason = reason

    def __repr__(self) -> str:
        if self.skipped:
            return f"BuildResult({self.container_name}, skipped={self.reason})"
        elif self.success:
            return f"BuildResult({self.container_name}, success=True)"
        else:
            return f"BuildResult({self.container_name}, success=False, error={self.error})"


class ParallelBuilder:
    """Execute container builds in parallel."""

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize parallel builder.

        Args:
            max_workers: Maximum number of parallel workers.
                        If None, defaults to (CPU count - 1) or 1.
        """
        if max_workers is None:
            cpu_count = os.cpu_count() or 2
            max_workers = max(1, cpu_count - 1)

        self.max_workers = max_workers
        self._completed: Set[str] = set()
        self._failed: Set[str] = set()
        self._lock = Lock()

        logger.info(f"Parallel builder initialized with {max_workers} workers")

    def _mark_completed(self, container_name: str, success: bool) -> None:
        """Mark container as completed.

        Args:
            container_name: Name of container
            success: Whether build succeeded
        """
        with self._lock:
            if success:
                self._completed.add(container_name)
            else:
                self._failed.add(container_name)

    def _is_ready_to_build(self, task: BuildTask) -> tuple[bool, str]:
        """Check if task dependencies are satisfied.

        Args:
            task: Build task to check

        Returns:
            Tuple of (ready, reason)
        """
        with self._lock:
            for dep in task.depends_on:
                if dep in self._failed:
                    return (False, f"dependency_failed:{dep}")
            for dep in task.depends_on:
                if dep not in self._completed:
                    return (False, f"waiting_for:{dep}")
            return (True, "ready")

    def build_sequential_groups(
        self,
        task_groups: List[List[BuildTask]],
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[BuildResult]:
        """Build groups of tasks sequentially, with parallelism within each group.

        Args:
            task_groups: List of task groups (each group can be built in parallel)
            progress_callback: Optional callback(status, current, total)

        Returns:
            List of build results
        """
        all_results = []
        total_tasks = sum(len(group) for group in task_groups)
        completed_count = 0

        for group_idx, group in enumerate(task_groups):
            logger.info(
                f"Building group {group_idx + 1}/{len(task_groups)} "
                f"({len(group)} containers)"
            )

            group_results = self.build_parallel(group, progress_callback)
            all_results.extend(group_results)

            completed_count += len(group)

            failed_in_group = [r for r in group_results if not r.success and not r.skipped]
            if failed_in_group:
                logger.error(
                    f"Group {group_idx + 1} had {len(failed_in_group)} failures, "
                    f"stopping build"
                )
                for remaining_group in task_groups[group_idx + 1:]:
                    for task in remaining_group:
                        all_results.append(BuildResult(
                            task.container_name,
                            success=False,
                            skipped=True,
                            reason="previous_group_failed"
                        ))
                break

        return all_results

    def build_parallel(
        self,
        tasks: List[BuildTask],
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[BuildResult]:
        """Build tasks in parallel (assumes no dependencies between tasks).

        Args:
            tasks: List of build tasks
            progress_callback: Optional callback(status, current, total)

        Returns:
            List of build results
        """
        if not tasks:
            return []

        results = []
        total = len(tasks)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task: Dict[Future, BuildTask] = {}
            for task in tasks:
                future = executor.submit(self._execute_task, task)
                future_to_task[future] = task
            for idx, future in enumerate(as_completed(future_to_task), 1):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results.append(result)
                    if progress_callback:
                        status = "success" if result.success else "failed"
                        if result.skipped:
                            status = "skipped"
                        progress_callback(status, idx, total)
                except Exception as e:
                    logger.exception(f"Unexpected error building {task.container_name}")
                    result = BuildResult(
                        task.container_name,
                        success=False,
                        error=e
                    )
                    results.append(result)
                    if progress_callback:
                        progress_callback("error", idx, total)
        return results

    def _execute_task(self, task: BuildTask) -> BuildResult:
        """Execute a single build task.

        Args:
            task: Build task to execute

        Returns:
            Build result
        """
        container_name = task.container_name

        ready, reason = self._is_ready_to_build(task)
        if not ready:
            logger.warning(f"Skipping {container_name}: {reason}")
            return BuildResult(
                container_name,
                success=False,
                skipped=True,
                reason=reason
            )

        try:
            logger.info(f"Building {container_name}")
            success = task.build_func()

            self._mark_completed(container_name, success)

            return BuildResult(
                container_name,
                success=success,
                reason="build_completed" if success else "build_failed"
            )

        except Exception as e:
            logger.exception(f"Error building {container_name}")
            self._mark_completed(container_name, False)

            return BuildResult(
                container_name,
                success=False,
                error=e
            )

    def reset(self) -> None:
        """Reset builder state (completed/failed sets)."""
        with self._lock:
            self._completed.clear()
            self._failed.clear()
