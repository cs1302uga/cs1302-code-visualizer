"""Errors related to code visualization.

Normative References:
    PEP 257 – Docstring Conventions (https://peps.python.org/pep-0257/)
    PEP 484 – Type Hints (https://peps.python.org/pep-0484/)
    PEP 678 – Enriching Exceptions with Notes (https://peps.python.org/pep-0678/)
"""

from __future__ import annotations

import inspect
import textwrap
from subprocess import CalledProcessError
from typing import cast


class CodeVisError(Exception):
    """Represents a code visualization error."""

    def __init__(self, message: str) -> None:
        """Initialize a CodeVisError with a message."""
        super().__init__(message)


class CodeVisTraceGeneratorError(CodeVisError):
    """A code visualization error related to tracing the code."""

    def __init__(
        self,
        source_code: str = "",
        cli_args: list[str] | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_status: int = 1,
    ) -> None:
        """Initialize a CodeVisTraceGeneratorError."""
        super().__init__("Unable to generate code execution trace.")
        self._source_code: str = source_code
        self._cli_args: list[str] = cli_args if cli_args is not None else []
        self._stdout: str = stdout if stdout is not None else ""
        self._stderr: str = stderr if stderr is not None else ""
        self._exit_status: int = exit_status

    @property
    def source_code(self) -> str:
        """The source code that was being traced."""
        return self._source_code

    @property
    def cli_args(self) -> list[str]:
        """The command-line arguments supplied to the trace generator."""
        return self._cli_args

    @property
    def stdout(self) -> str:
        """The output that the trace generator sent to standard output."""
        return self._stdout

    @property
    def stderr(self) -> str:
        """The output that the trace generator sent to standard error."""
        return self._stderr

    @property
    def exit_status(self) -> int:
        """The exit status of trace generator."""
        return self._exit_status

    def with_property_notes(self: CodeVisTraceGeneratorError) -> CodeVisTraceGeneratorError:
        """Return this CodeVisTraceGeneratorError with property notes added."""

        def isproperty(obj: object) -> bool:
            """Return `True` if `obj` is a `property`, else `False`."""
            return isinstance(obj, property)

        members: list[tuple[str, property]] = inspect.getmembers(
            CodeVisTraceGeneratorError, isproperty
        )

        for name, member in members:
            if doc := inspect.getdoc(member):
                note_heading: str = doc.strip().rstrip(".")
                note_body: str = textwrap.indent(
                    str(getattr(self, name, "<unknown note>")), " " * 2
                )
                note: str = textwrap.indent("\n" + note_heading + ":\n\n" + note_body, " " * 2)
                self.add_note(note)

        return self

    @staticmethod
    def from_cpe(
        cpe: CalledProcessError,
        source_code: str,
        cli_args: list[str],
    ) -> CodeVisTraceGeneratorError:
        """Return a CodeVisTraceGeneratorError for the supplied CalledProcessError."""
        stdout: str | None = cast(str | None, cpe.stdout)
        stderr: str | None = cast(str | None, cpe.stderr)
        return CodeVisTraceGeneratorError(
            source_code=source_code,
            cli_args=cli_args,
            stdout=stdout,
            stderr=stderr,
            exit_status=cpe.returncode,
        ).with_property_notes()


class CodeVisRenderError(CodeVisError):
    """An error related to rendering the image for a visualization."""

    def __init__(self, message: str) -> None:
        """Initialize a CodeVisRenderError with a message."""
        super().__init__(message)


class TracerDownloadError(CodeVisError):
    """An error occurring while downloading, verifying, or caching the tracer JAR."""

    def __init__(self, message: str) -> None:
        """Initialize a TracerDownloadError with a message."""
        super().__init__(message)


class BreakpointResolutionError(CodeVisError):
    """An error occurring while discovering or resolving breakpoints."""

    def __init__(self, message: str) -> None:
        """Initialize a BreakpointResolutionError with a message."""
        super().__init__(message)


class JDKInstallationError(CodeVisError):
    """An error occurring while downloading, extracting, or verifying the JDK."""

    def __init__(self, message: str) -> None:
        """Initialize a JDKInstallationError with a message."""
        super().__init__(message)


# Domain-level aliases
CodeVisualizerError = CodeVisError
TraceGeneratorError = CodeVisTraceGeneratorError
RenderError = CodeVisRenderError
JDKError = JDKInstallationError
