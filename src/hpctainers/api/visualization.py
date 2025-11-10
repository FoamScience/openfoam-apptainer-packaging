"""DAG visualization for container builds.

Provides visualization of container build dependencies using graphviz.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class DAGVisualizer:
    """Visualize container build DAG.

    Creates visual representations of container dependencies using graphviz.
    """

    def __init__(self):
        """Initialize visualizer."""
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str]] = []
        self._graphviz_available = self._check_graphviz()

    def _check_graphviz(self) -> bool:
        """Check if graphviz is available.

        Returns:
            True if graphviz is available
        """
        try:
            import graphviz
            return True
        except ImportError:
            logger.warning(
                "graphviz not available - install with: pip install graphviz"
            )
            return False

    def add_node(
        self,
        name: str,
        node_type: str = "container",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a node to the DAG.

        Args:
            name: Node name (container name)
            node_type: Type of node (mpi, framework, project)
            metadata: Additional metadata for the node
        """
        self.nodes[name] = {
            "type": node_type,
            "metadata": metadata or {}
        }
        logger.debug(f"Added node: {name} ({node_type})")

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a dependency edge.

        Args:
            from_node: Source node (dependency)
            to_node: Target node (depends on from_node)
        """
        self.edges.append((from_node, to_node))
        logger.debug(f"Added edge: {from_node} -> {to_node}")

    def render(
        self,
        output_path: Path,
        format: str = "svg",
        engine: str = "dot",
        view: bool = False
    ) -> Path:
        """Render the DAG to a file.

        Args:
            output_path: Output file path (without extension)
            format: Output format (svg, png, pdf, etc.)
            engine: Graphviz engine (dot, neato, fdp, etc.)
            view: Whether to open the rendered file

        Returns:
            Path to rendered file

        Raises:
            ImportError: If graphviz is not available
            RuntimeError: If rendering fails
        """
        if not self._graphviz_available:
            raise ImportError(
                "graphviz not available. Install with: pip install graphviz"
            )

        import graphviz

        dot = graphviz.Digraph(
            name='container_dag',
            engine=engine,
            format=format
        )

        dot.attr(
            rankdir='TB',  # Top to bottom
            splines='ortho',  # Orthogonal edges
            nodesep='0.5',
            ranksep='0.8'
        )

        for name, info in self.nodes.items():
            node_type = info['type']
            metadata = info['metadata']

            if node_type == 'mpi':
                color = 'lightblue'
                shape = 'box'
                label = f"MPI: {name}"
            elif node_type == 'framework':
                color = 'lightgreen'
                shape = 'box'
                label = f"Framework: {name}"
            elif node_type == 'project':
                color = 'lightyellow'
                shape = 'box'
                label = f"Project: {name}"
            else:
                color = 'lightgray'
                shape = 'ellipse'
                label = name

            if metadata:
                details = []
                if 'os' in metadata:
                    os_info = metadata['os']
                    if hasattr(os_info, 'distro'):
                        details.append(f"{os_info.distro}:{os_info.version}")
                if 'mpi' in metadata:
                    mpi_info = metadata['mpi']
                    if hasattr(mpi_info, 'implementation'):
                        details.append(f"{mpi_info.implementation} {mpi_info.version}")
                if 'framework' in metadata:
                    fw_info = metadata['framework']
                    if hasattr(fw_info, 'definition'):
                        details.append(f"{fw_info.definition} {fw_info.version}")

                if details:
                    label = f"{label}\\n" + "\\n".join(details)

            dot.node(
                name,
                label=label,
                style='filled',
                fillcolor=color,
                shape=shape
            )

        for from_node, to_node in self.edges:
            dot.edge(from_node, to_node)

        output_path = Path(output_path)
        output_dir = output_path.parent
        output_name = output_path.stem

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            rendered_path = dot.render(
                filename=output_name,
                directory=output_dir,
                cleanup=True,  # Remove .dot file after rendering
                view=view
            )
            logger.info(f"DAG visualization saved to: {rendered_path}")
            return Path(rendered_path)

        except Exception as e:
            raise RuntimeError(f"Failed to render DAG: {e}") from e

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram syntax.

        Returns:
            Mermaid diagram as string

        Example:
            >>> visualizer = DAGVisualizer()
            >>> visualizer.add_node("base", "mpi")
            >>> visualizer.add_node("app", "framework")
            >>> visualizer.add_edge("base", "app")
            >>> print(visualizer.to_mermaid())
        """
        lines = ["graph TD"]

        for name, info in self.nodes.items():
            node_type = info['type']
            safe_name = name.replace('-', '_')

            if node_type == 'mpi':
                lines.append(f"    {safe_name}[MPI: {name}]")
                lines.append(f"    style {safe_name} fill:#add8e6")
            elif node_type == 'framework':
                lines.append(f"    {safe_name}[Framework: {name}]")
                lines.append(f"    style {safe_name} fill:#90ee90")
            elif node_type == 'project':
                lines.append(f"    {safe_name}[Project: {name}]")
                lines.append(f"    style {safe_name} fill:#ffffe0")
            else:
                lines.append(f"    {safe_name}[{name}]")

        for from_node, to_node in self.edges:
            safe_from = from_node.replace('-', '_')
            safe_to = to_node.replace('-', '_')
            lines.append(f"    {safe_from} --> {safe_to}")

        return '\n'.join(lines)

    def to_dot(self) -> str:
        """Generate DOT (Graphviz) syntax.

        Returns:
            DOT diagram as string
        """
        lines = [
            "digraph container_dag {",
            "  rankdir=TB;",
            "  splines=ortho;",
            "  nodesep=0.5;",
            "  ranksep=0.8;",
            ""
        ]

        for name, info in self.nodes.items():
            node_type = info['type']

            if node_type == 'mpi':
                style = 'shape=box, style=filled, fillcolor=lightblue'
                label = f"MPI: {name}"
            elif node_type == 'framework':
                style = 'shape=box, style=filled, fillcolor=lightgreen'
                label = f"Framework: {name}"
            elif node_type == 'project':
                style = 'shape=box, style=filled, fillcolor=lightyellow'
                label = f"Project: {name}"
            else:
                style = 'shape=ellipse, style=filled, fillcolor=lightgray'
                label = name

            lines.append(f'  "{name}" [label="{label}", {style}];')

        lines.append("")

        for from_node, to_node in self.edges:
            lines.append(f'  "{from_node}" -> "{to_node}";')

        lines.append("}")
        return '\n'.join(lines)

    def get_build_order(self) -> List[Set[str]]:
        """Get topological build order (parallel groups).

        Returns:
            List of sets, where each set contains nodes that can be built in parallel
        """
        in_degree = {node: 0 for node in self.nodes}
        children = {node: [] for node in self.nodes}

        for from_node, to_node in self.edges:
            children[from_node].append(to_node)
            in_degree[to_node] += 1

        build_order = []
        ready = {node for node, degree in in_degree.items() if degree == 0}

        while ready:
            build_order.append(ready.copy())
            next_ready = set()
            for node in ready:
                for child in children[node]:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        next_ready.add(child)

            ready = next_ready

        return build_order

    def clear(self) -> None:
        """Clear all nodes and edges."""
        self.nodes.clear()
        self.edges.clear()
        logger.debug("DAG cleared")


def visualize_dependency_graph(
    graph: Any,
    output_path: Path,
    format: str = "svg"
) -> Path:
    """Visualize a DependencyGraph object.

    Args:
        graph: DependencyGraph instance
        output_path: Output file path
        format: Output format (svg, png, pdf)

    Returns:
        Path to rendered file
    """
    from hpctainers.lib.dependency_graph import ContainerType

    visualizer = DAGVisualizer()

    for node_name, node_info in graph.nodes.items():
        node_type_map = {
            ContainerType.MPI: "mpi",
            ContainerType.FRAMEWORK: "framework",
            ContainerType.PROJECT: "project"
        }
        node_type = node_type_map.get(node_info.container_type, "container")

        visualizer.add_node(
            node_name,
            node_type=node_type,
            metadata=node_info.metadata
        )

    for node_name, node_info in graph.nodes.items():
        for dep in node_info.depends_on:
            visualizer.add_edge(dep, node_name)

    return visualizer.render(output_path, format=format)
