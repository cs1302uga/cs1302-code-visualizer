"""TODO."""

from pprint import pformat
from textwrap import indent
import colorama
import termcolor

from argparse import Namespace
from subprocess import CalledProcessError
from typing import Self

colorama.init(
    autoreset=True,
    wrap=True,
)


class CodeVisError(Exception):
    """Represents an code visualization error."""

    def __init__(self, message: str) -> Self:
        super().__init__(message)


class CodeVisTraceGeneratorError(Exception):
    """An error related to compiling and running the code being used
    for a visualization.
    """

    def __init__(
        self,
        source_code: str,
        cli_args: Namespace,
        stdout: str,
        stderr: str,
        exit_status: int,
    ) -> Self:
        super().__init__("Unable to generate code execution trace.")
        self._source_code = source_code
        self._cli_args = cli_args
        self._stdout = stdout
        self._stderr = stderr
        self._exit_status = exit_status

    @property
    def source_code(self) -> src:
        """The source code that was being traced."""
        return self._source_code

    @property
    def cli_args(self) -> Namespace:
        """The command-line arguments supplied to the trace generator."""
        return self._cli_args

    @property
    def stdout(self) -> src:
        """The output that the trace generator sent to standard output."""
        return self._stdout

    @property
    def stderr(self) -> src:
        """The output that the trace generator sent to standard error."""
        return self._stderr

    @property
    def exit_status(self) -> int:
        """The exit status of trace generator."""
        return self._exit_status

    @staticmethod
    def _note_with_heading(heading: str, note: str, src: bool = False) -> str:
        rich_heading = "".join(
            [
                colorama.Style.BRIGHT,
                colorama.Fore.CYAN,
                heading + ":",
            ]
        )

        rich_note = "".join(
            [
                (colorama.Style.DIM + f"{i:2} " if src else " " * 2)
                + colorama.Style.NORMAL
                + colorama.Fore.BLUE
                + line
                + "\n"
                for i, line in enumerate(note.splitlines(), start=1)
            ]
        )

        return f"\n{rich_heading}\n{rich_note}".rstrip()

    def with_attribute_note(self, *names: str) -> CodeVisTraceGeneratorError:
        for name in names:
            attribute_note = getattr(self, name)
            if not isinstance(attribute_note, str):
                attribute_note = pformat(attribute_note)
            if not len(attribute_note):
                attribute_note: str = "None"
            note: str = CodeVisTraceGeneratorError._note_with_heading(
                heading=getattr(type(self), name).__doc__.strip()[0:-1],
                note=attribute_note,
                src=name in ["source_code"],
            )
            self.add_note(note)
        return self

    @staticmethod
    def from_cpe(
        cpe: CalledProcessError,
        source_code: str,
        cli_args: Namespace,
    ) -> CodeVisTraceGeneratorError:
        
        exc = CodeVisTraceGeneratorError(
            source_code=source_code,
            cli_args=cli_args,
            stdout=cpe.stdout,
            stderr=cpe.stderr,
            exit_status=cpe.returncode,
        ).with_attribute_note(
            "source_code",
            "cli_args",
            "stdout",
            "stderr",
            "exit_status",
        )
        return exc


class CodeVisRenderError(Exception):
    """An error related to rendering the image for a visualization."""

    def __init__(self, message: str) -> Self:
        super().__init__(message)
