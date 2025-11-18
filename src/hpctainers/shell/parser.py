"""Parser for shell pipe syntax.

Parses commands like: container | from ubuntu:24.04 | with-exec apt-get update
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass
from typing import Any, List

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """Represents a single command in the pipe chain."""

    name: str
    args: List[str]
    kwargs: dict[str, Any]

    def __repr__(self) -> str:
        """String representation."""
        args_str = ', '.join(repr(a) for a in self.args)
        kwargs_str = ', '.join(f'{k}={v!r}' for k, v in self.kwargs.items())
        params = ', '.join(filter(None, [args_str, kwargs_str]))
        return f"Command({self.name!r}, [{params}])"


class PipelineParser:
    """Parser for pipe-based command syntax.

    Converts shell syntax like:
        container | from ubuntu:24.04 | with-exec apt-get update

    To a list of Command objects that can be translated to Python API calls.
    """

    def __init__(self):
        """Initialize parser."""
        pass

    def parse(self, command_line: str) -> List[Command]:
        """Parse a command line into a list of commands.

        Args:
            command_line: Command line to parse (e.g., "container | from ubuntu")

        Returns:
            List of Command objects

        Raises:
            ValueError: If parsing fails
        """
        parts = self._split_pipeline(command_line)

        commands = []
        for part in parts:
            cmd = self._parse_command(part.strip())
            commands.append(cmd)

        return commands

    def _split_pipeline(self, command_line: str) -> List[str]:
        """Split command line by pipes, respecting quotes.

        Args:
            command_line: Command line to split

        Returns:
            List of command parts
        """
        parts = []
        current = []
        in_quotes = False
        quote_char = None

        for char in command_line:
            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
                current.append(char)
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current.append(char)
            elif char == '|' and not in_quotes:
                parts.append(''.join(current))
                current = []
            else:
                current.append(char)

        if current:
            parts.append(''.join(current))

        return parts

    def _parse_command(self, command_str: str) -> Command:
        """Parse a single command into Command object.

        Args:
            command_str: Command string (e.g., "from ubuntu:24.04")

        Returns:
            Command object
        """
        try:
            tokens = shlex.split(command_str)
        except ValueError as e:
            raise ValueError(f"Failed to parse command: {command_str}") from e

        if not tokens:
            raise ValueError("Empty command")

        name = tokens[0]

        args = []
        kwargs = {}

        for token in tokens[1:]:
            if '=' in token:
                key, value = token.split('=', 1)
                value = value.strip('"\'')
                kwargs[key] = value
            else:
                args.append(token)

        return Command(name=name, args=args, kwargs=kwargs)

    def to_python_code(self, commands: List[Command]) -> str:
        """Convert command list to Python code string.

        Args:
            commands: List of Command objects

        Returns:
            Python code as string

        Example:
            >>> parser = PipelineParser()
            >>> commands = parser.parse("container | from ubuntu:24.04")
            >>> code = parser.to_python_code(commands)
            >>> print(code)
            dag.container().from_("ubuntu:24.04")
        """
        if not commands:
            return ""

        parts = []

        for i, cmd in enumerate(commands):
            method_name = self._command_to_method(cmd.name)

            args_str = ', '.join(repr(arg) for arg in cmd.args)
            kwargs_str = ', '.join(f'{k}={v!r}' for k, v in cmd.kwargs.items())
            params = ', '.join(filter(None, [args_str, kwargs_str]))

            if i == 0:
                if method_name in ('container', 'directory'):
                    parts.append(f"dag.{method_name}({params})")
                else:
                    parts.append(f"{method_name}({params})")
            else:
                parts.append(f"{method_name}({params})")

        return '.'.join(parts)

    def _command_to_method(self, command_name: str) -> str:
        """Convert shell command name to Python method name.

        Converts kebab-case to snake_case and handles Python keywords.

        Args:
            command_name: Command name (e.g., "with-exec", "from")

        Returns:
            Python method name (e.g., "with_exec", "from_")
        """
        method_name = command_name.replace('-', '_')

        python_keywords = {'from', 'import', 'class', 'def', 'return', 'if', 'else', 'elif', 'while', 'for', 'in', 'is', 'not', 'and', 'or'}
        if method_name in python_keywords:
            method_name += '_'

        return method_name

    def _method_to_command(self, method_name: str) -> str:
        """Convert Python method name to shell command name.

        Converts snake_case to kebab-case.

        Args:
            method_name: Method name (e.g., "with_exec")

        Returns:
            Shell command name (e.g., "with-exec")
        """
        return method_name.replace('_', '-')


def parse_pipeline(command_line: str) -> List[Command]:
    """Parse a pipeline command line.

    Convenience function that creates a parser and parses the command.

    Args:
        command_line: Command line to parse

    Returns:
        List of Command objects
    """
    parser = PipelineParser()
    return parser.parse(command_line)
