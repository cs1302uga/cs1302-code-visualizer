"""Shared array presentation options for Python and command-line renderers."""

import argparse
from collections.abc import Mapping
from typing import Any, Literal

ArrayOrientation = Literal["horizontal", "vertical"]


def validate_array_options(
    array_orientation: str = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate and copy array settings, without requiring IDs to exist in a trace."""
    if array_orientation not in ("horizontal", "vertical"):
        raise ValueError("array_orientation must be 'horizontal' or 'vertical'")
    if not isinstance(alternate_array_orientations, bool):
        raise TypeError("alternate_array_orientations must be a boolean")
    if array_orientations is not None and not isinstance(array_orientations, Mapping):
        raise TypeError("array_orientations must be an object mapping heap IDs to orientations")
    overrides = dict(array_orientations) if array_orientations is not None else {}
    for object_id, orientation in overrides.items():
        if not isinstance(object_id, str) or not object_id.strip():
            raise ValueError("array_orientations keys must be nonempty heap ID strings")
        if orientation not in ("horizontal", "vertical"):
            raise ValueError(
                f"array_orientations[{object_id!r}] must be 'horizontal' or 'vertical'"
            )
    return {
        "array_orientation": array_orientation,
        "alternate_array_orientations": alternate_array_orientations,
        "array_orientations": overrides,
    }


def _parse_override(value: str) -> tuple[str, str]:
    object_id, separator, orientation = value.partition("=")
    if not separator or not object_id.strip() or orientation not in ("horizontal", "vertical"):
        raise argparse.ArgumentTypeError("expected HEAP_ID=horizontal or HEAP_ID=vertical")
    return object_id, orientation


def add_array_arguments(parser: argparse.ArgumentParser) -> None:
    """Register the same array flags on each rendering command."""
    parser.add_argument(
        "--array-orientation",
        choices=("horizontal", "vertical"),
        default="horizontal",
        help="Base array orientation (default: horizontal); the 1D orientation when alternating.",
    )
    parser.add_argument(
        "--alternate-array-orientations",
        action="store_true",
        help="Flip array orientation for each additional dimension (default: off).",
    )
    parser.add_argument(
        "--array-orientation-for",
        action="append",
        type=_parse_override,
        metavar="HEAP_ID=ORIENTATION",
        help="Override one array's orientation; repeatable, last value for an ID wins.",
    )


def array_options_from_args(
    args: argparse.Namespace,
    job: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge command defaults and optional job settings, with job overrides winning."""
    defaults = validate_array_options(
        getattr(args, "array_orientation", "horizontal"),
        getattr(args, "alternate_array_orientations", False),
        dict(getattr(args, "array_orientation_for", None) or []),
    )
    if job is None:
        return defaults
    # Validate job fields before merging so malformed maps produce a useful error.
    settings = validate_array_options(
        job.get("array_orientation", defaults["array_orientation"]),
        job.get("alternate_array_orientations", defaults["alternate_array_orientations"]),
        job.get("array_orientations", {}),
    )
    if "array_orientations" in job and job["array_orientations"] is None:
        raise ValueError("array_orientations must be an object, not null")
    settings["array_orientations"] = {
        **defaults["array_orientations"],
        **settings["array_orientations"],
    }
    return settings
