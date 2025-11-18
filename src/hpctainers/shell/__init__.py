"""Shell module for interactive container-as-code CLI.

Provides a Dagger-style shell interface with pipe syntax, REPL, and built-in
commands for interactive container development.
"""

from __future__ import annotations

from hpctainers.shell.builtins import execute_builtin, is_builtin
from hpctainers.shell.interpreter import ExecutionContext, get_context, reset_context
from hpctainers.shell.parser import PipelineParser, parse_pipeline
from hpctainers.shell.repl import REPL, run_command, run_repl, run_script

__all__ = [
    "REPL",
    "PipelineParser",
    "ExecutionContext",
    "run_repl",
    "run_command",
    "run_script",
    "parse_pipeline",
    "get_context",
    "reset_context",
    "is_builtin",
    "execute_builtin",
]
