"""Shared utilities and common helpers for dependency installers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated

import click
import requests
import typer
from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

console = Console()
err_console = Console(stderr=True)


def find_project_root(start_dir: Path | None = None) -> Path:
    """Locate the project root directory containing pyproject.toml.

    Args:
        start_dir: Optional starting directory. Defaults to this file's directory.

    Returns:
        The Path to the directory containing pyproject.toml, or the current
        working directory if not found.
    """
    current = (start_dir or Path(__file__).resolve().parent).resolve()
    while current != current.parent:
        if (current / "pyproject.toml").is_file():
            return current
        current = current.parent
    return Path.cwd()


def get_project_version(root_dir: Path) -> str:
    """Read the project version from pyproject.toml if present.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Version string from pyproject.toml, or '0.2.0' as fallback.
    """
    toml_path = root_dir / "pyproject.toml"
    if toml_path.is_file():
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
                return str(data.get("project", {}).get("version", "0.2.0"))
        except (OSError, tomllib.TOMLDecodeError):  # pragma: no cover
            return "0.2.0"
    return "0.2.0"


def get_min_system_dependency_version(root_dir: Path, dep_name: str) -> str | None:
    """Read minimum version for a dependency from tool.cs1302book.system-dependencies.

    Args:
        root_dir: Root directory of the project.
        dep_name: Name of system dependency (e.g. 'graphviz', 'plantuml').

    Returns:
        Version string, or None if not found.
    """
    toml_path = root_dir / "pyproject.toml"
    if not toml_path.is_file():
        return None

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
            deps = (
                data
                .get("tool", {})
                .get("cs1302book", {})
                .get("system-dependencies", {})
                .get("system-dependencies", [])
            )
            for req_str in deps:
                try:
                    req = Requirement(req_str)
                    if req.name == dep_name:
                        for spec in req.specifier:
                            if spec.operator in (">=", "=="):
                                return spec.version
                except InvalidRequirement:
                    continue
    except (OSError, tomllib.TOMLDecodeError):  # pragma: no cover
        return None
    return None


def get_configured_dependencies(root_dir: Path) -> dict[str, str]:
    """Read all system dependencies from tool.cs1302book.system-dependencies.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Dictionary mapping dependency name to required minimum version.
    """
    toml_path = root_dir / "pyproject.toml"
    if not toml_path.is_file():
        return {"graphviz": "15.1.0", "plantuml": "1.2026.1", "jdk": "25"}

    deps_map: dict[str, str] = {}
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
            deps = (
                data
                .get("tool", {})
                .get("cs1302book", {})
                .get("system-dependencies", {})
                .get("system-dependencies", [])
            )
            for req_str in deps:
                try:
                    req = Requirement(req_str)
                    for spec in req.specifier:
                        if spec.operator in (">=", "=="):
                            deps_map[req.name] = spec.version
                            break
                    if req.name not in deps_map:
                        deps_map[req.name] = "latest"
                except InvalidRequirement:
                    continue
    except (OSError, tomllib.TOMLDecodeError):  # pragma: no cover
        return {"graphviz": "15.1.0", "plantuml": "1.2026.1", "jdk": "25"}

    if not deps_map:
        deps_map = {"graphviz": "15.1.0", "plantuml": "1.2026.1", "jdk": "25"}
    return deps_map


def resolve_default_bin_dir(root: Path) -> Path:
    """Resolve the default binary launcher directory (.venv/bin if available).

    Args:
        root: Project root directory.

    Returns:
        Path to .venv/bin, .venv/Scripts, or scripts/installer/shims/bin.
    """
    venv_bin = root / ".venv" / "bin"
    if not venv_bin.is_dir() and (root / ".venv" / "Scripts").is_dir():
        venv_bin = root / ".venv" / "Scripts"
    return venv_bin if venv_bin.is_dir() else (root / "scripts" / "installer" / "shims" / "bin")


def resolve_shims_bin_dir(root: Path) -> Path:
    """Resolve the static shims binary directory (scripts/installer/shims/bin).

    Args:
        root: Project root directory.

    Returns:
        Path to scripts/installer/shims/bin.
    """
    return root / "scripts" / "installer" / "shims" / "bin"


def resolve_default_man_dir(root: Path) -> Path:
    """Resolve the default man pages directory (.venv/share/man if available).

    Args:
        root: Project root directory.

    Returns:
        Path to .venv/share/man or scripts/installer/shims/share/man.
    """
    venv_dir = root / ".venv"
    if venv_dir.is_dir():
        return venv_dir / "share" / "man"
    return root / "scripts" / "installer" / "shims" / "share" / "man"


def resolve_shims_man_dir(root: Path) -> Path:
    """Resolve the static shims man pages directory (scripts/installer/shims/share/man).

    Args:
        root: Project root directory.

    Returns:
        Path to scripts/installer/shims/share/man.
    """
    return root / "scripts" / "installer" / "shims" / "share" / "man"


def format_path_for_display(path: Path | None) -> str:
    """Format a filesystem path for clean console output.

    Args:
        path: Path object to format, or None.

    Returns:
        String with ~ or ./ relative notation if appropriate, or 'none' if None.
    """
    if path is None:
        return "none"
    abs_path = path.resolve() if path.exists() else path.absolute()
    home = Path.home().resolve()
    cwd = Path.cwd().resolve()

    if abs_path == home:
        return "~"

    try:
        rel_cwd = abs_path.relative_to(cwd)
        if len(str(rel_cwd)) < len(str(abs_path)):
            return f"./{rel_cwd}"
    except ValueError:
        pass

    try:
        rel_home = abs_path.relative_to(home)
        return f"~/{rel_home}"
    except ValueError:
        pass

    return str(abs_path)


def clean_version_tag(tag: str) -> str:
    """Strip 'v', 'jdk-', or other prefixes from version tags.

    Args:
        tag: Raw version tag.

    Returns:
        Clean version string (e.g. '16.0.0', '25.0.4+7').
    """
    cleaned = tag.strip()
    if cleaned.lower().startswith("jdk-"):
        cleaned = cleaned[4:]
    elif cleaned.lower().startswith("jdk"):
        cleaned = cleaned[3:]
    if cleaned.lower().startswith("v"):
        cleaned = cleaned[1:]
    return cleaned


def is_version_ge(v1_str: str | None, v2_str: str | None) -> bool:
    """Check if version v1 is greater than or equal to version v2.

    Args:
        v1_str: First version string.
        v2_str: Second version string.

    Returns:
        True if v1 >= v2, False otherwise.
    """
    if not v1_str or not v2_str:
        return False
    try:
        return Version(clean_version_tag(v1_str)) >= Version(clean_version_tag(v2_str))
    except InvalidVersion:
        return clean_version_tag(v1_str) == clean_version_tag(v2_str)


def download_file(
    url: str,
    dest_path: Path,
    description: str = "Downloading",
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Download a remote file with a Rich progress bar.

    Args:
        url: Remote URL to download.
        dest_path: Local destination file path.
        description: Description text for the progress bar.
        dry_run: If True, simulates download without network transfer.
        verbose: Verbose logging flag.

    Returns:
        True if download succeeded (or dry-run), False otherwise.
    """
    if dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would download {url} -> {format_path_for_display(dest_path)}[/yellow]"
        )
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")

    if verbose:
        err_console.print(f"[dim]GET {url}[/dim]")

    try:
        response = requests.get(
            url,
            stream=True,
            timeout=30,
            headers={"User-Agent": "cs1302-book-installer/1.0"},
        )
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=err_console,
        ) as progress:
            task_id = progress.add_task(description, total=total_size if total_size > 0 else None)
            with open(temp_dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))

        temp_dest.replace(dest_path)
        return True
    except (requests.RequestException, OSError) as e:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        if verbose:
            err_console.print(f"[red]Download error:[/red] {e}")
        return False


def render_help(
    app: typer.Typer,
    command_name: str | None,
    ctx: typer.Context | None,
    cli_name: str,
) -> None:
    """Render help information for Typer app or a specific subcommand.

    Args:
        app: Typer application instance.
        command_name: Specific subcommand name, or None for general help.
        ctx: Typer Context.
        cli_name: Program name for display.

    Raises:
        typer.Exit: Exits after printing help.
    """
    root_ctx = ctx.find_root() if ctx else None
    cli_obj = typer.main.get_command(app)

    if not command_name:
        with click.Context(cli_obj, info_name=cli_name) as click_ctx:
            console.print(cli_obj.get_help(click_ctx))
        raise typer.Exit(0)

    subcommand = None
    if hasattr(cli_obj, "get_command"):
        subcommand = cli_obj.get_command(click.Context(cli_obj), command_name)
    elif hasattr(cli_obj, "commands") and isinstance(cli_obj.commands, dict):
        subcommand = cli_obj.commands.get(command_name)
    elif getattr(cli_obj, "name", None) == command_name:
        subcommand = cli_obj

    if not subcommand:
        err_console.print(f"[red]error:[/red] Unknown command '{command_name}'")
        raise typer.Exit(1)

    with click.Context(
        subcommand,
        info_name=command_name,
        parent=click.Context(cli_obj, info_name=cli_name),
    ) as click_ctx:
        console.print(subcommand.get_help(click_ctx))
    raise typer.Exit(0)


# Common CLI Option Type Aliases
OptVerbose = Annotated[
    bool,
    typer.Option(
        "-v",
        "--verbose",
        help="Enable verbose output and diagnostics",
    ),
]
OptDryRun = Annotated[
    bool,
    typer.Option(
        "-n",
        "--dry-run",
        help="Show what actions would be taken without making changes",
    ),
]
OptForce = Annotated[
    bool,
    typer.Option(
        "-f",
        "--force",
        help="Force re-download / overwrite even if version exists in cache",
    ),
]
OptYes = Annotated[
    bool,
    typer.Option(
        "-y",
        "--yes",
        help="Automatic yes to prompts; assume yes to all questions",
    ),
]
OptDir = Annotated[
    Path | None,
    typer.Option(
        "--dir",
        help="Install directory override",
    ),
]
OptCacheDir = Annotated[
    Path | None,
    typer.Option(
        "--cache-dir",
        help="Cache directory override",
    ),
]
OptBinDir = Annotated[
    Path | None,
    typer.Option(
        "--bin-dir",
        help="Launcher binary directory override",
    ),
]
OptShort = Annotated[
    bool,
    typer.Option(
        "--short",
        "-s",
        help="Print only the version number",
    ),
]
OptPurge = Annotated[
    bool,
    typer.Option(
        "--purge",
        "--all",
        "-a",
        help="Also delete all cached version directories and downloaded archives.",
    ),
]
