"""Built-in commands for the shell.

Provides special commands like .help, .wait, .inspect, etc.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


class BuiltinCommand:
    """Base class for built-in commands."""

    def __init__(self, name: str, description: str, func: Callable):
        """Initialize builtin command.

        Args:
            name: Command name (with or without leading dot)
            description: Help text
            func: Function to execute
        """
        self.name = name.lstrip('.')
        self.description = description
        self.func = func

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the command.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Command result
        """
        return self.func(*args, **kwargs)


class BuiltinRegistry:
    """Registry of built-in shell commands."""

    def __init__(self):
        """Initialize registry."""
        self.commands: Dict[str, BuiltinCommand] = {}
        self._register_defaults()

    def register(self, name: str, description: str) -> Callable:
        """Decorator to register a built-in command.

        Args:
            name: Command name
            description: Help text

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            cmd = BuiltinCommand(name, description, func)
            self.commands[cmd.name] = cmd
            logger.debug(f"Registered builtin: .{cmd.name}")
            return func
        return decorator

    def get(self, name: str) -> BuiltinCommand | None:
        """Get a built-in command.

        Args:
            name: Command name (with or without leading dot)

        Returns:
            Command if found, None otherwise
        """
        name = name.lstrip('.')
        return self.commands.get(name)

    def list_commands(self) -> list[BuiltinCommand]:
        """List all built-in commands.

        Returns:
            List of commands
        """
        return list(self.commands.values())

    def _register_defaults(self) -> None:
        """Register default built-in commands."""
        pass


_registry = BuiltinRegistry()


def get_registry() -> BuiltinRegistry:
    """Get the global builtin registry.

    Returns:
        Registry instance
    """
    return _registry


@_registry.register("help", "Show help for available commands and methods")
def help_command(method_name: str = None, context: Any = None) -> str:
    """Show help information.

    Args:
        method_name: Optional method name to show help for (e.g., "build", "with-mpi")
        context: Execution context (unused, for compatibility)

    Returns:
        Help text
    """
    if method_name is None:
        lines = [
            "hpctainers Shell - Container-as-Code Interactive CLI",
            "",
            "Available built-in commands (prefix with .):",
            ""
        ]

        for cmd in _registry.list_commands():
            lines.append(f"  .{cmd.name:<15} {cmd.description}")

        lines.extend([
            "",
            "Pipeline syntax:",
            "  container | from ubuntu:24.04 | with-exec apt-get update",
            "",
            "Variable assignment:",
            "  $mpi = container | from ubuntu | with-mpi openmpi 4.1.5",
            "",
            "Use .help <method> for method-specific help (e.g., .help build)",
            "Use .list to see all available methods",
            "Use .exit or Ctrl+D to quit",
        ])

        return '\n'.join(lines)
    else:
        from hpctainers.api import dag
        method_name_py = method_name.replace('-', '_')
        python_keywords = {'from', 'import', 'class', 'def', 'return'}
        if method_name_py in python_keywords:
            method_name_py += '_'
        container_obj = dag.container()
        if hasattr(container_obj, method_name_py):
            method = getattr(container_obj, method_name_py)
            if hasattr(method, '__doc__') and method.__doc__:
                return f"Help for '{method_name}':\n\n{method.__doc__}"
            else:
                return f"Method '{method_name}' found but has no documentation"
        else:
            return f"No method '{method_name}' found in Container API\n\nUse .list to see all available methods"


@_registry.register("wait", "Wait for async operations to complete")
def wait_command(obj: Any = None, context: Any = None) -> Any:
    """Wait for operations to complete.

    In the current implementation, operations are synchronous,
    so this is a no-op placeholder for future async support.

    Args:
        obj: Optional object to wait on
        context: Execution context (unused, for compatibility)

    Returns:
        The object unchanged
    """
    logger.info("Waiting for operations to complete...")
    # TODO: Implement async waiting if/when lazy execution is added
    return obj


@_registry.register("inspect", "Inspect object properties and methods")
def inspect_command(obj: Any = None, context: Any = None) -> str:
    """Inspect an object.

    Args:
        obj: Object to inspect
        context: Execution context (unused, for compatibility)

    Returns:
        Inspection report
    """
    if obj is None:
        return "No object to inspect. Use: .inspect after a pipeline (e.g., $var | .inspect)"

    lines = [
        f"Object: {type(obj).__name__}",
        "",
        "Methods:",
    ]
    methods = [m for m in dir(obj) if not m.startswith('_') and callable(getattr(obj, m))]
    for method in sorted(methods):
        method_obj = getattr(obj, method)
        if hasattr(method_obj, '__doc__') and method_obj.__doc__:
            doc_first_line = method_obj.__doc__.split('\n')[0].strip()
            lines.append(f"  .{method}() - {doc_first_line}")
        else:
            lines.append(f"  .{method}()")
    properties = [p for p in dir(obj) if not p.startswith('_') and not callable(getattr(obj, p))]
    if properties:
        lines.extend(["", "Properties:"])
        for prop in sorted(properties):
            lines.append(f"  {prop}")

    return '\n'.join(lines)


@_registry.register("list", "List available methods for container API")
def list_command(obj: Any = None, context: Any = None) -> str:
    """List available methods.

    Args:
        obj: Object to list methods for (or None for Container API methods)
        context: Execution context (unused, for compatibility)

    Returns:
        Method list
    """
    from hpctainers.api import dag

    if obj is None:
        container_obj = dag.container()
        obj = container_obj

    methods = [m for m in dir(obj) if not m.startswith('_') and callable(getattr(obj, m))]

    lines = ["Available Container API methods:", ""]
    for method in sorted(methods):
        method_obj = getattr(obj, method)
        if hasattr(method_obj, '__doc__') and method_obj.__doc__:
            doc_lines = method_obj.__doc__.strip().split('\n')
            first_line = doc_lines[0].strip()
            shell_name = method.replace('_', '-').rstrip('-')  # Remove trailing dash from "from_"
            lines.append(f"  {shell_name:<20} {first_line}")
        else:
            shell_name = method.replace('_', '-').rstrip('-')
            lines.append(f"  {shell_name}")

    lines.append("")
    lines.append("Use .help <method> for detailed help (e.g., .help build)")

    return '\n'.join(lines)


@_registry.register("exit", "Exit the shell")
def exit_command(context: Any = None) -> None:
    """Exit the shell.

    Args:
        context: Execution context (unused, for compatibility)

    Raises:
        SystemExit: To exit the shell
    """
    logger.info("Exiting shell...")
    raise SystemExit(0)


@_registry.register("vars", "List all variables")
def vars_command(context: Any = None) -> str:
    """List all variables.

    Args:
        context: Execution context

    Returns:
        Variable listing
    """
    if context is None:
        from hpctainers.shell.interpreter import get_context
        context = get_context()

    variables = context.interpreter.list_variables()

    if not variables:
        return "No variables defined"

    lines = ["Variables:"]
    for name, value in variables.items():
        value_str = str(type(value).__name__)
        lines.append(f"  ${name} = {value_str}")

    return '\n'.join(lines)


@_registry.register("history", "Show command history")
def history_command(context: Any = None) -> str:
    """Show command history.

    Args:
        context: Execution context

    Returns:
        History listing
    """
    if context is None:
        from hpctainers.shell.interpreter import get_context
        context = get_context()

    history = context.get_history()

    if not history:
        return "No command history"

    lines = ["Command history:"]
    for i, cmd in enumerate(history, 1):
        lines.append(f"  {i}. {cmd}")

    return '\n'.join(lines)


@_registry.register("visualize", "Visualize container dependency DAG")
def visualize_command(output: str = "mermaid", context: Any = None) -> str:
    """Visualize container dependency graph.

    Usage:
        .visualize mermaid          # Output Mermaid diagram to console
        .visualize dot              # Output DOT syntax to console
        .visualize graph.svg        # Render to SVG file (requires graphviz)
        .visualize graph.png        # Render to PNG file (requires graphviz)

    Args:
        output: Output format or file path
            - "mermaid": Output Mermaid diagram text
            - "dot": Output DOT syntax text
            - file with .svg/.png/.pdf extension: Render to file using graphviz
        context: Execution context

    Returns:
        Visualization output or status message
    """
    from pathlib import Path
    from hpctainers.api.visualization import DAGVisualizer
    from hpctainers.api.container import ContainerImpl

    if context is None:
        from hpctainers.shell.interpreter import get_context
        context = get_context()

    variables = context.interpreter.list_variables()
    containers = {name: obj for name, obj in variables.items()
                  if isinstance(obj, ContainerImpl)}

    if not containers:
        return "No containers defined. Create containers using:\n  $var = container | from ubuntu:24.04 | ..."

    viz = DAGVisualizer()
    for var_name, container in containers.items():
        if container.frameworks:
            node_type = "project"
        elif container.mpi_impl:
            node_type = "mpi"
        else:
            node_type = "simple"
        metadata = {
            "name": container.name or var_name,
            "base_image": container.base_image
        }
        if container.mpi_impl:
            metadata["mpi"] = f"{container.mpi_impl} {container.mpi_version}"
        if container.frameworks:
            metadata["frameworks"] = ", ".join(
                f"{fw['definition']} {fw['version']}" for fw in container.frameworks
            )

        viz.add_node(container.name or var_name, node_type=node_type, metadata=metadata)

        if container.frameworks and container.mpi_impl:
            framework_name = f"{container.mpi_impl}-{container.frameworks[0]['definition']}"
            for other_name, other_container in containers.items():
                if (other_container.mpi_impl == container.mpi_impl and
                    other_container.frameworks and
                    other_container.frameworks[0]['definition'] == container.frameworks[0]['definition']):
                    viz.add_edge(other_container.name or other_name, container.name or var_name)
                    break
            else:
                for other_name, other_container in containers.items():
                    if (other_container.mpi_impl == container.mpi_impl and
                        not other_container.frameworks):
                        viz.add_edge(other_container.name or other_name, container.name or var_name)
                        break

    output_lower = output.lower()
    if output_lower == "mermaid":
        return viz.to_mermaid()
    elif output_lower == "dot":
        return viz.to_dot()
    elif output_lower.endswith(('.svg', '.png', '.pdf')):
        output_path = Path(output)
        format = output_path.suffix.lstrip('.')
        try:
            viz.to_graphviz(output_path, format=format)
            return f"✓ Visualization saved to {output_path}"
        except ImportError:
            return "Error: graphviz not installed. Install with: pip install graphviz\n" \
                   "Or use text formats: .visualize mermaid or .visualize dot"
        except Exception as e:
            return f"Error rendering visualization: {e}"

    else:
        return f"Unknown output format: {output}\n" \
               "Valid formats: mermaid, dot, or file path (.svg, .png, .pdf)"


@_registry.register("config", "Configure build settings (pull, cache, etc.)")
def config_command(args: str = None, context: Any = None) -> str:
    """Configure build settings.

    Usage:
        .config                          # Show current settings
        .config pull.enabled=true        # Enable/disable pulling
        .config pull.protocol=oras       # Set pull protocol (oras, docker, library)
        .config pull.scope=ghcr.io/org   # Set registry scope
        .config cache.enabled=true       # Enable/disable cache
        .config force_rebuild=true       # Enable/disable force rebuild

    Args:
        args: Configuration setting (key=value)
        context: Execution context

    Returns:
        Status message
    """
    from hpctainers.api.builder import get_builder, reset_builder

    builder = get_builder()

    if args is None:
        lines = ["Current build configuration:", ""]
        lines.append(f"  pull.enabled     = {builder.registry.try_to_pull}")
        lines.append(f"  pull.protocol    = {builder.registry.protocol}")
        lines.append(f"  pull.scope       = {builder.registry.scope}")
        lines.append(f"  cache.enabled    = {builder.cache is not None}")
        if builder.cache is not None:
            lines.append(f"  cache.dir        = {builder.cache.cache_dir}")
        lines.append(f"  containers_dir   = {builder.containers_dir}")
        lines.append("")
        lines.append("Use .config <key>=<value> to change settings")
        lines.append("Example: .config pull.enabled=false")
        return '\n'.join(lines)

    if '=' not in args:
        return f"Invalid config format. Use: .config key=value\nExample: .config pull.enabled=false"

    key, value = args.split('=', 1)
    key = key.strip()
    value = value.strip()

    if value.lower() in ('true', 'yes', '1'):
        value_bool = True
    elif value.lower() in ('false', 'no', '0'):
        value_bool = False
    else:
        value_bool = None

    current_settings = {
        'cache_enabled': builder.cache is not None,
        'try_pull': builder.registry.try_to_pull,
        'protocol': builder.registry.protocol,
        'scope': builder.registry.scope,
        'containers_dir': builder.containers_dir,
        'force_rebuild': False  # Not exposed currently
    }

    if key == 'pull.enabled':
        if value_bool is None:
            return f"Invalid boolean value: {value}. Use true or false"
        current_settings['try_pull'] = value_bool
        message = f"Pull enabled: {value_bool}"
    elif key == 'pull.protocol':
        valid_protocols = ['oras', 'docker', 'library']
        if value not in valid_protocols:
            return f"Invalid protocol: {value}. Must be one of: {', '.join(valid_protocols)}"
        current_settings['protocol'] = value
        message = f"Pull protocol: {value}"
    elif key == 'pull.scope':
        current_settings['scope'] = value
        message = f"Registry scope: {value}"
    elif key == 'cache.enabled':
        if value_bool is None:
            return f"Invalid boolean value: {value}. Use true or false"
        current_settings['cache_enabled'] = value_bool
        message = f"Cache enabled: {value_bool}"
    elif key == 'force_rebuild':
        if value_bool is None:
            return f"Invalid boolean value: {value}. Use true or false"
        current_settings['force_rebuild'] = value_bool
        message = f"Force rebuild: {value_bool}"
    else:
        return f"Unknown config key: {key}\nValid keys: pull.enabled, pull.protocol, pull.scope, cache.enabled, force_rebuild"

    reset_builder(
        containers_dir=current_settings['containers_dir'],
        cache_enabled=current_settings['cache_enabled'],
        try_pull=current_settings['try_pull'],
        force_rebuild=current_settings['force_rebuild'],
        protocol=current_settings['protocol'],
        scope=current_settings['scope']
    )

    return f"✓ {message}\n  (Builder configuration updated)"


def is_builtin(command: str) -> bool:
    """Check if a command is a built-in.

    Args:
        command: Command name

    Returns:
        True if builtin
    """
    return _registry.get(command) is not None


def execute_builtin(command: str, args: str = None, *extra_args: Any, **kwargs: Any) -> Any:
    """Execute a built-in command.

    Args:
        command: Command name
        args: Argument string (e.g., "build" for ".help build")
        *extra_args: Additional positional arguments
        **kwargs: Keyword arguments

    Returns:
        Command result

    Raises:
        ValueError: If command not found
    """
    cmd = _registry.get(command)
    if cmd is None:
        raise ValueError(f"Unknown built-in command: {command}")

    if args:
        return cmd.execute(args, *extra_args, **kwargs)
    else:
        return cmd.execute(*extra_args, **kwargs)
