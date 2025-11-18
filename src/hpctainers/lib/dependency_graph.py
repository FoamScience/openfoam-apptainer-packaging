"""Dependency graph for container builds.

Analyzes container dependencies, computes build order,
and generates visualizations.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ContainerType(Enum):
    """Type of container in the build pipeline."""
    MPI = "mpi"
    FRAMEWORK = "framework"
    PROJECT = "project"


@dataclass
class ContainerNode:
    """Represents a container in the dependency graph."""

    name: str
    container_type: ContainerType
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, ContainerNode):
            return False
        return self.name == other.name


class DependencyGraph:
    """Dependency graph for container builds."""

    def __init__(self):
        """Initialize empty dependency graph."""
        self.nodes: Dict[str, ContainerNode] = {}
        self.edges: Dict[str, List[str]] = defaultdict(list)

    def add_node(
        self,
        name: str,
        container_type: ContainerType,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, any]] = None
    ) -> None:
        """Add a node to the graph.

        Args:
            name: Container name
            container_type: Type of container
            depends_on: List of container names this depends on
            metadata: Optional metadata dictionary
        """
        depends_on = depends_on or []
        metadata = metadata or {}

        node = ContainerNode(
            name=name,
            container_type=container_type,
            depends_on=depends_on,
            metadata=metadata
        )

        self.nodes[name] = node

        for dep in depends_on:
            self.edges[dep].append(name)

    def get_build_order(self) -> List[str]:
        """Compute topological sort for build order.

        Returns:
            List of container names in build order

        Raises:
            ValueError: If graph contains cycles
        """
        in_degree = {name: 0 for name in self.nodes}

        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep in in_degree:
                    in_degree[node.name] += 1

        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        build_order = []

        while queue:
            current = queue.popleft()
            build_order.append(current)

            for dependent in self.edges[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(build_order) != len(self.nodes):
            remaining = set(self.nodes.keys()) - set(build_order)
            raise ValueError(f"Dependency cycle detected involving: {remaining}")

        return build_order

    def get_parallel_groups(self) -> List[List[str]]:
        """Group containers that can be built in parallel.

        Returns:
            List of groups, where each group can be built concurrently
        """
        in_degree = {name: len(node.depends_on) for name, node in self.nodes.items()}

        groups = []
        remaining = set(self.nodes.keys())

        while remaining:
            current_group = [
                name for name in remaining
                if all(dep not in remaining for dep in self.nodes[name].depends_on)
            ]

            if not current_group:
                raise ValueError("Cannot determine parallel groups - possible cycle")

            groups.append(sorted(current_group))  # Sort for consistency
            remaining -= set(current_group)

        return groups

    def get_dependencies(self, container_name: str, recursive: bool = False) -> Set[str]:
        """Get dependencies for a container.

        Args:
            container_name: Name of container
            recursive: If True, get all transitive dependencies

        Returns:
            Set of container names this container depends on
        """
        if container_name not in self.nodes:
            return set()

        if not recursive:
            return set(self.nodes[container_name].depends_on)

        visited = set()
        queue = deque([container_name])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            if current in self.nodes:
                for dep in self.nodes[current].depends_on:
                    if dep not in visited:
                        queue.append(dep)

        visited.discard(container_name)
        return visited

    def get_dependents(self, container_name: str, recursive: bool = False) -> Set[str]:
        """Get containers that depend on this container.

        Args:
            container_name: Name of container
            recursive: If True, get all transitive dependents

        Returns:
            Set of container names that depend on this container
        """
        if container_name not in self.nodes:
            return set()

        if not recursive:
            return set(self.edges[container_name])

        visited = set()
        queue = deque([container_name])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dependent in self.edges[current]:
                if dependent not in visited:
                    queue.append(dependent)

        visited.discard(container_name)
        return visited

    def to_dot(self, highlight_cache_hits: Optional[Set[str]] = None) -> str:
        """Generate GraphViz DOT format representation.

        Args:
            highlight_cache_hits: Set of container names that hit cache

        Returns:
            DOT format string
        """
        highlight_cache_hits = highlight_cache_hits or set()

        lines = ['digraph ContainerBuildDAG {']
        lines.append('    rankdir=TB;')
        lines.append('    node [shape=box, style=rounded];')
        lines.append('')

        for name, node in self.nodes.items():
            if node.container_type == ContainerType.MPI:
                color = 'lightblue'
            elif node.container_type == ContainerType.FRAMEWORK:
                color = 'lightgreen'
            else:  # PROJECT
                color = 'lightyellow'

            style = 'filled,rounded'
            if name in highlight_cache_hits:
                style = 'filled,rounded,bold'
                color = 'lightgray'

            label = name
            if name in highlight_cache_hits:
                label += '\\n(cached)'

            lines.append(
                f'    "{name}" [label="{label}", fillcolor={color}, style="{style}"];'
            )

        lines.append('')

        for name, node in self.nodes.items():
            for dep in node.depends_on:
                lines.append(f'    "{dep}" -> "{name}";')

        lines.append('}')
        return '\n'.join(lines)

    def export_dot(
        self,
        output_path: Path,
        highlight_cache_hits: Optional[Set[str]] = None
    ) -> None:
        """Export graph to DOT file.

        Args:
            output_path: Path to output .dot file
            highlight_cache_hits: Set of container names that hit cache
        """
        dot_content = self.to_dot(highlight_cache_hits)

        with open(output_path, 'w') as f:
            f.write(dot_content)

        logger.info(f"Exported dependency graph to {output_path}")

    def export_svg(
        self,
        output_path: Path,
        highlight_cache_hits: Optional[Set[str]] = None
    ) -> bool:
        """Export graph to SVG file using graphviz.

        Args:
            output_path: Path to output .svg file
            highlight_cache_hits: Set of container names that hit cache

        Returns:
            True if export succeeded, False if graphviz not available
        """
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
            dot_content = self.to_dot(highlight_cache_hits)
            f.write(dot_content)
            dot_file = f.name

        try:
            result = subprocess.run(
                ['dot', '-Tsvg', dot_file, '-o', str(output_path)],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Exported dependency graph to {output_path}")
            return True

        except FileNotFoundError:
            logger.warning("graphviz 'dot' command not found. Install graphviz to export SVG.")
            return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate SVG: {e.stderr}")
            return False

        finally:
            Path(dot_file).unlink(missing_ok=True)
