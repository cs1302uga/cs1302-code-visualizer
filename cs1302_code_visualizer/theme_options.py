"""Shared presentation theme validation."""

import argparse
from typing import Literal, TypedDict

Theme = Literal["light", "dark", "auto"]


class ThemeOptions(TypedDict, total=False):
    """Optional rendering keyword, retaining its name for static checking."""

    theme: Theme


def theme_options(theme: Theme | None) -> ThemeOptions:
    """Validate a theme and omit an unspecified host-inherited choice."""
    if theme is None:
        return {}
    if theme not in ("light", "dark", "auto"):
        raise ValueError("theme must be light, dark, or auto")
    return {"theme": theme}


def add_theme_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared optional theme selector."""
    parser.add_argument(
        "--theme",
        choices=("light", "dark", "auto"),
        default=None,
        help="Visualization theme (default: light export, host theme inline).",
    )
