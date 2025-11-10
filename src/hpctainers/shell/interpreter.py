"""Shell interpreter for executing parsed commands.

Translates parsed command pipelines into Python API calls and executes them.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from hpctainers.api import dag
from hpctainers.shell.parser import Command, PipelineParser

logger = logging.getLogger(__name__)


class ShellInterpreter:
    """Interprets and executes shell commands using the Python API.

    This class takes parsed Command objects and executes them by calling
    the appropriate Python API methods.
    """

    def __init__(self):
        """Initialize interpreter."""
        self.parser = PipelineParser()
        self.variables: Dict[str, Any] = {}
        self._last_result: Any = None

    def execute(self, command_line: str) -> Any:
        """Execute a command line.

        Args:
            command_line: Command line to execute

        Returns:
            Result of execution

        Raises:
            RuntimeError: If execution fails
        """
        if '=' in command_line and not command_line.strip().startswith('container'):
            return self._handle_assignment(command_line)
        commands = self.parser.parse(command_line)
        if not commands:
            return None
        try:
            result = self._execute_pipeline(commands)
            self._last_result = result
            return result
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            raise RuntimeError(f"Failed to execute: {command_line}") from e

    def _handle_assignment(self, command_line: str) -> None:
        """Handle variable assignment (e.g., $foo = container | ...).

        Args:
            command_line: Command line with assignment
        """
        if '=' in command_line:
            var_part, pipeline_part = command_line.split('=', 1)
            var_name = var_part.strip().lstrip('$')
            pipeline = pipeline_part.strip()
            result = self.execute(pipeline)
            self.variables[var_name] = result
            logger.debug(f"Variable assigned: ${var_name}")

    def _execute_pipeline(self, commands: list[Command]) -> Any:
        """Execute a pipeline of commands.

        Args:
            commands: List of commands to execute

        Returns:
            Result of final command
        """
        current_object = None

        for i, cmd in enumerate(commands):
            method_name = self._command_to_method(cmd.name)

            if i == 0:
                if cmd.name.startswith('$'):
                    var_name = cmd.name.lstrip('$')
                    if var_name not in self.variables:
                        raise ValueError(f"Variable ${var_name} not defined")
                    current_object = self.variables[var_name]
                elif method_name == 'container':
                    current_object = dag.container()
                elif method_name == 'directory':
                    current_object = dag.directory()
                else:
                    raise ValueError(
                        f"Pipeline must start with 'container', 'directory', or a variable, got '{cmd.name}'"
                    )
            else:
                if not hasattr(current_object, method_name):
                    raise AttributeError(
                        f"Object has no method '{method_name}'"
                    )

                method = getattr(current_object, method_name)

                try:
                    if method_name in ('with_exec',) and cmd.args:
                        current_object = method(cmd.args, **cmd.kwargs)
                    else:
                        current_object = method(*cmd.args, **cmd.kwargs)
                except TypeError as e:
                    raise TypeError(
                        f"Invalid arguments for {method_name}: {e}"
                    ) from e

        return current_object

    def _command_to_method(self, command_name: str) -> str:
        """Convert shell command to Python method name.

        Converts kebab-case to snake_case and handles Python keywords.

        Args:
            command_name: Shell command name (kebab-case)

        Returns:
            Python method name (snake_case)
        """
        method_name = command_name.replace('-', '_')

        python_keywords = {'from', 'import', 'class', 'def', 'return', 'if', 'else', 'elif', 'while', 'for', 'in', 'is', 'not', 'and', 'or'}
        if method_name in python_keywords:
            method_name += '_'

        return method_name

    def get_last_result(self) -> Any:
        """Get the last execution result.

        Returns:
            Last result
        """
        return self._last_result

    def get_variable(self, name: str) -> Any:
        """Get a variable value.

        Args:
            name: Variable name (without $)

        Returns:
            Variable value

        Raises:
            KeyError: If variable not found
        """
        return self.variables[name]

    def list_variables(self) -> dict[str, Any]:
        """List all variables.

        Returns:
            Dictionary of variables
        """
        return self.variables.copy()

    def clear_variables(self) -> None:
        """Clear all variables."""
        self.variables.clear()
        logger.debug("Variables cleared")


class ExecutionContext:
    """Execution context for shell commands.

    Maintains state across multiple command executions, including variables,
    history, and configuration.
    """

    def __init__(self):
        """Initialize execution context."""
        self.interpreter = ShellInterpreter()
        self.history: list[str] = []
        self.output_format: str = "text"  # text, json, yaml

    def execute(self, command_line: str) -> Any:
        """Execute command and update history.

        Args:
            command_line: Command to execute

        Returns:
            Execution result
        """
        self.history.append(command_line)
        return self.interpreter.execute(command_line)

    def get_history(self) -> list[str]:
        """Get command history.

        Returns:
            List of executed commands
        """
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear command history."""
        self.history.clear()


_context: Optional[ExecutionContext] = None


def get_context() -> ExecutionContext:
    """Get or create global execution context.

    Returns:
        Execution context
    """
    global _context
    if _context is None:
        _context = ExecutionContext()
    return _context


def reset_context() -> None:
    """Reset global execution context."""
    global _context
    _context = ExecutionContext()
