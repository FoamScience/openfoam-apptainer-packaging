"""REPL (Read-Eval-Print Loop) for interactive shell.

Provides an interactive command-line interface for executing container
build commands.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from hpctainers.shell.builtins import execute_builtin, is_builtin
from hpctainers.shell.interpreter import ExecutionContext

logger = logging.getLogger(__name__)

try:
    import readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False
    logger.debug("readline not available - command history disabled")


class REPL:
    """Read-Eval-Print Loop for interactive shell.

    Provides an interactive command-line interface similar to Dagger Shell.
    """

    def __init__(
        self,
        context: Optional[ExecutionContext] = None,
        prompt: str = "hpctainers> "
    ):
        """Initialize REPL.

        Args:
            context: Execution context (creates new if None)
            prompt: Command prompt string
        """
        self.context = context or ExecutionContext()
        self.prompt = prompt
        self.running = False

        if HAS_READLINE:
            self._setup_readline()

    def _setup_readline(self) -> None:
        """Setup readline for command history and completion."""
        history_file = Path.home() / ".hpctainers_history"
        try:
            readline.read_history_file(str(history_file))
        except FileNotFoundError:
            pass

        import atexit
        atexit.register(readline.write_history_file, str(history_file))

        readline.set_history_length(1000)

        # TODO: Add tab completion
        # readline.set_completer(self._completer)
        # readline.parse_and_bind("tab: complete")

    def run(self) -> None:
        """Run the REPL loop."""
        self.running = True
        self._print_welcome()
        while self.running:
            try:
                line = input(self.prompt).strip()
                if not line:
                    continue
                self._execute_line(line)
            except EOFError:
                # Ctrl+D
                print()  # Newline
                break
            except KeyboardInterrupt:
                # Ctrl+C
                print()  # Newline
                continue
            except SystemExit:
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                print(f"Error: {e}", file=sys.stderr)
        self._print_goodbye()

    def _print_welcome(self) -> None:
        """Print welcome message."""
        print("hpctainers Shell - Container-as-Code Interactive CLI")
        print("Type .help for available commands")
        print()

    def _print_goodbye(self) -> None:
        """Print goodbye message."""
        print("Goodbye!")

    def _execute_line(self, line: str) -> None:
        """Execute a single line of input.

        Args:
            line: Input line
        """
        if line.startswith('.'):
            command_parts = line[1:].split(None, 1)
            command_name = command_parts[0]

            if is_builtin(command_name):
                args_str = command_parts[1] if len(command_parts) > 1 else None
                result = execute_builtin(command_name, args=args_str, context=self.context)
                if result is not None:
                    print(result)
                return

        try:
            result = self.context.execute(line)
            if result is not None:
                self._print_result(result)

        except Exception as e:
            logger.exception("Execution failed")
            print(f"Error: {e}", file=sys.stderr)

    def _print_result(self, result: any) -> None:
        """Print execution result.

        Args:
            result: Result to print
        """
        if isinstance(result, str):
            if '\n' in result:
                print(result)
            else:
                print(f"⇒ {result}")
        elif isinstance(result, Path):
            print(f"⇒ Path")
            print(f"  {result}")
        elif hasattr(result, '__class__'):
            class_name = result.__class__.__name__
            print(f"⇒ {class_name}")
        else:
            print(f"⇒ {result}")


def run_repl(context: Optional[ExecutionContext] = None) -> None:
    """Run interactive REPL.

    Args:
        context: Optional execution context
    """
    repl = REPL(context=context)
    repl.run()


def run_command(command: str, context: Optional[ExecutionContext] = None) -> any:
    """Run a single command non-interactively.

    Args:
        command: Command to execute
        context: Optional execution context

    Returns:
        Command result
    """
    if context is None:
        context = ExecutionContext()

    if command.startswith('.'):
        command_parts = command[1:].split(None, 1)
        command_name = command_parts[0]
        if is_builtin(command_name):
            args_str = command_parts[1] if len(command_parts) > 1 else None
            return execute_builtin(command_name, args=args_str, context=context)

    return context.execute(command)


def run_script(script_path: Path, context: Optional[ExecutionContext] = None) -> None:
    """Run commands from a script file.

    Args:
        script_path: Path to script file
        context: Optional execution context
    """
    if context is None:
        context = ExecutionContext()

    with open(script_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            if not line or line.startswith('#'):
                continue

            try:
                logger.debug(f"Executing line {line_num}: {line}")
                result = run_command(line, context)

                if result is not None:
                    print(f"Line {line_num}: {result}")

            except Exception as e:
                logger.error(f"Error on line {line_num}: {e}")
                print(f"Error on line {line_num}: {e}", file=sys.stderr)
                raise
