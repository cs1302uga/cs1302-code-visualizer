"""String presentation and deprecated rendering-option compatibility."""

import argparse
import warnings
from collections.abc import Mapping
from typing import Any, Literal, cast

StringStyle = Literal["compact", "default", "inline"]


class _Omitted:
    """Distinguish omitted arguments from explicit default values."""

    def __repr__(self) -> str:
        """Keep compatibility signatures readable and stable."""
        return "<omitted>"


OMITTED = _Omitted()


def resolve_string_style(
    string_style: StringStyle | _Omitted = OMITTED,
    inline_strings: bool | _Omitted = OMITTED,
    *,
    stacklevel: int = 3,
) -> StringStyle:
    """Validate presentation settings and translate the deprecated boolean."""
    if not isinstance(inline_strings, _Omitted):
        if not isinstance(string_style, _Omitted):
            raise TypeError("inline_strings and string_style cannot both be supplied")
        if not isinstance(inline_strings, bool):
            raise TypeError("inline_strings must be a boolean")
        warnings.warn(
            "inline_strings is deprecated for rendering; use string_style='inline' "
            "or 'default'. It will be removed in the next major release.",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
        return "inline" if inline_strings else "default"
    if isinstance(string_style, _Omitted):
        return "default"
    if string_style not in ("compact", "default", "inline"):
        raise ValueError("string_style must be 'compact', 'default', or 'inline'")
    return cast(StringStyle, string_style)


def add_string_argument(parser: argparse.ArgumentParser) -> None:
    """Register string presentation on a rendering command."""
    parser.add_argument(
        "--string-style",
        choices=("compact", "default", "inline"),
        default="default",
        help="String presentation (default: default, separate heap objects).",
    )


def string_options_from_args(
    args: argparse.Namespace,
    job: Mapping[str, Any] | None = None,
) -> dict[str, StringStyle]:
    """Resolve per-job presentation, inheriting the CLI default when omitted."""
    if job is not None and ("string_style" in job or "inline_strings" in job):
        style = resolve_string_style(
            job.get("string_style", OMITTED),
            job.get("inline_strings", OMITTED),
        )
    else:
        style = resolve_string_style(getattr(args, "string_style", "default"))
    return {"string_style": style}
