#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "click>=8.0.0",
#     "packaging>=24.0",
#     "requests>=2.31.0",
#     "rich>=13.7.0",
#     "typer>=0.12.0",
# ]
# ///
"""Unified system dependencies installation and status manager.

Interactively checks and installs required system dependencies (Graphviz, PlantUML, JDK, Enchant, UV)
configured under tool.cs1302book.system-dependencies in pyproject.toml.
"""

from __future__ import annotations

import enum
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

# Ensure project root is on sys.path when running as a standalone PEP 723 script
_project_root = Path(__file__).resolve().parent
while _project_root != _project_root.parent:  # pragma: no cover
    if (_project_root / "pyproject.toml").is_file():
        if str(_project_root) not in sys.path:
            sys.path.insert(0, str(_project_root))
        break
    _project_root = _project_root.parent

import typer
from rich.console import Console
from rich.table import Table

from scripts.installer import enchant, graphviz, jdk, plantuml, uv
from scripts.installer.common import (
    OptBinDir,
    OptCacheDir,
    OptDir,
    OptDryRun,
    OptForce,
    OptPurge,
    OptShort,
    OptVerbose,
    OptYes,
    find_project_root,
    get_configured_dependencies,
    get_project_version,
    is_version_ge,
    render_help,
    resolve_shims_bin_dir,
    resolve_shims_man_dir,
)
from scripts.installer.graphviz import OptManDir

console = Console()
err_console = Console(stderr=True)


class DepStatus(enum.Enum):
    """Status categorization for a system dependency."""

    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    BELOW_MIN = "below_min"
    NOT_INSTALLED = "not_installed"


@dataclass
class DependencyInfo:
    """Metadata and inspection status for a single system dependency.

    Attributes:
        name: Name of the system dependency (e.g. 'enchant', 'graphviz', 'plantuml', 'jdk', 'uv').
        installed_version: Currently linked version string, or None if missing.
        required_version: Configured minimum version requirement from pyproject.toml.
        latest_version: Latest upstream version from provider, or None if unavailable.
        status: Calculated DepStatus enum value.
    """

    name: str
    installed_version: str | None
    required_version: str | None
    latest_version: str | None
    status: DepStatus

    @property
    def status_label(self) -> str:
        """Formatted human-readable status string with markup."""
        if self.status == DepStatus.UP_TO_DATE:
            return "[green]✓ Up to date[/green]"
        if self.status == DepStatus.UPDATE_AVAILABLE:
            return f"[yellow]↑ Update available ({self.installed_version} -> {self.latest_version})[/yellow]"
        if self.status == DepStatus.BELOW_MIN:
            return f"[red]✗ Outdated (< {self.required_version})[/red]"
        return "[red]✗ Not installed[/red]"

    @property
    def needs_install(self) -> bool:
        """Whether this dependency is missing or below the project required version."""
        return self.status in (DepStatus.NOT_INSTALLED, DepStatus.BELOW_MIN)


def inspect_dependency(
    name: str,
    required_version: str | None,
    cfg_graphviz: graphviz.Config,
    cfg_plantuml: plantuml.Config,
    cfg_jdk: jdk.Config,
    cfg_enchant: enchant.Config,
    cfg_uv: uv.Config,
) -> DependencyInfo:
    """Inspect current installation and upstream version for a dependency.

    Args:
        name: Name of dependency ('enchant', 'graphviz', 'plantuml', 'jdk', or 'uv').
        required_version: Required minimum version string.
        cfg_graphviz: Configuration for Graphviz installer.
        cfg_plantuml: Configuration for PlantUML installer.
        cfg_jdk: Configuration for JDK installer.
        cfg_enchant: Configuration for Enchant installer.
        cfg_uv: Configuration for UV installer.

    Returns:
        DependencyInfo containing current status.
    """
    if name == "graphviz":
        installed = graphviz.get_installed_version(cfg_graphviz.current_link)
        latest = graphviz.get_latest_gitlab_version()
    elif name == "plantuml":
        installed = plantuml.get_installed_version(cfg_plantuml.jar_symlink)
        latest = plantuml.get_latest_github_version()
    elif name == "enchant":
        installed = enchant.get_installed_version(cfg_enchant.current_link)
        latest = enchant.get_latest_github_version()
    elif name == "uv":
        installed = uv.get_installed_version(cfg_uv.current_link)
        if not installed:
            # Fall back to checking uv in bin_dir / PATH
            installed = uv.get_installed_version(cfg_uv.primary_executable)
        if not installed:
            # Fall back to which uv
            system_uv = shutil.which("uv")
            if system_uv:
                installed = uv.get_installed_version(Path(system_uv))
        latest = uv.get_latest_github_version()
    else:  # jdk / java
        installed = jdk.get_installed_version(cfg_jdk.current_link)
        default_major = (
            int(required_version.split(".")[0])
            if (required_version and required_version.split(".")[0].isdigit())
            else 25
        )
        latest = jdk.get_latest_jdk_version(default_major)

    if not installed:
        status = DepStatus.NOT_INSTALLED
    elif required_version and not is_version_ge(installed, required_version):
        status = DepStatus.BELOW_MIN
    elif latest and not is_version_ge(installed, latest):
        status = DepStatus.UPDATE_AVAILABLE
    else:
        status = DepStatus.UP_TO_DATE

    return DependencyInfo(
        name=name,
        installed_version=installed,
        required_version=required_version,
        latest_version=latest,
        status=status,
    )


def collect_all_dependencies_status(
    root: Path,
    cfg_graphviz: graphviz.Config,
    cfg_plantuml: plantuml.Config,
    cfg_jdk: jdk.Config,
    cfg_enchant: enchant.Config,
    cfg_uv: uv.Config,
    filter_names: list[str] | None = None,
) -> list[DependencyInfo]:
    """Collect status for all (or filtered) configured dependencies.

    Args:
        root: Project root directory.
        cfg_graphviz: Graphviz configuration.
        cfg_plantuml: PlantUML configuration.
        cfg_jdk: JDK configuration.
        cfg_enchant: Enchant configuration.
        cfg_uv: UV configuration.
        filter_names: Optional list of dependency names to filter by.

    Returns:
        List of DependencyInfo objects.
    """
    configured = get_configured_dependencies(root)
    names = list(configured.keys())
    if filter_names:
        clean_filters = [f.lower() for f in filter_names if f.lower() != "all"]
        if clean_filters:
            names = [n for n in names if n.lower() in clean_filters]

    infos: list[DependencyInfo] = []
    for name in names:
        req_ver = configured.get(name)
        info = inspect_dependency(
            name, req_ver, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv
        )
        infos.append(info)
    return infos


def render_dependencies_table(infos: list[DependencyInfo]) -> None:
    """Render a formatted Rich table of system dependencies status.

    Args:
        infos: List of DependencyInfo objects to display.
    """
    table = Table(title="System Dependencies Status", box=None)
    table.add_column("Dependency", style="bold cyan", width=14)
    table.add_column("Installed", style="cyan", width=14)
    table.add_column("Required", style="dim", width=14)
    table.add_column("Latest", style="green", width=14)
    table.add_column("Status", width=30)

    for info in infos:
        table.add_row(
            info.name,
            info.installed_version or "none",
            f">={info.required_version}" if info.required_version else "any",
            info.latest_version or "unknown",
            info.status_label,
        )

    console.print(table)
    console.print()


def execute_dependency_install(
    info: DependencyInfo,
    target_tag: str | None,
    cfg_graphviz: graphviz.Config,
    cfg_plantuml: plantuml.Config,
    cfg_jdk: jdk.Config,
    cfg_enchant: enchant.Config,
    cfg_uv: uv.Config,
) -> None:
    """Execute installation or upgrade for a specific dependency.

    Args:
        info: Target DependencyInfo object.
        target_tag: Optional specific version string to install.
        cfg_graphviz: Graphviz installer configuration.
        cfg_plantuml: PlantUML installer configuration.
        cfg_jdk: JDK installer configuration.
        cfg_enchant: Enchant installer configuration.
        cfg_uv: UV installer configuration.
    """
    tag = target_tag or info.required_version or info.latest_version or "latest"
    console.print(f"[bold cyan]Configuring {info.name} (target: {tag})...[/bold cyan]")
    if info.name == "graphviz":
        _ = graphviz.apply_version_link(tag, cfg_graphviz, is_explicit_use=bool(target_tag))
    elif info.name == "plantuml":
        _ = plantuml.apply_version_link(tag, cfg_plantuml, is_explicit_use=bool(target_tag))
    elif info.name == "enchant":
        enchant.apply_version_link(tag, cfg_enchant, is_explicit_use=bool(target_tag))
    elif info.name == "uv":
        uv.apply_version_link(tag, cfg_uv)
    elif info.name in ("jdk", "java"):
        _ = jdk.apply_version_link(tag, cfg_jdk, is_explicit_use=bool(target_tag))


def run_interactive_install(
    infos: list[DependencyInfo],
    force: bool,
    yes: bool,
    cfg_graphviz: graphviz.Config,
    cfg_plantuml: plantuml.Config,
    cfg_jdk: jdk.Config,
    cfg_enchant: enchant.Config,
    cfg_uv: uv.Config,
) -> None:
    """Interactively prompt and install missing or outdated dependencies.

    Args:
        infos: List of inspected dependencies.
        force: Whether to force installation.
        yes: Whether automatic confirmation is enabled.
        cfg_graphviz: Graphviz installer configuration.
        cfg_plantuml: PlantUML installer configuration.
        cfg_jdk: JDK installer configuration.
        cfg_enchant: Enchant installer configuration.
        cfg_uv: UV installer configuration.
    """
    to_install = [info for info in infos if info.needs_install or force]

    if not to_install:
        console.print(
            "[bold green]✓ All system dependencies are satisfied and up to date.[/bold green]"
        )
        return

    console.print(f"Found {len(to_install)} dependency/dependencies to configure:\n")

    for info in to_install:
        prompt_text = (
            f"Install missing {info.name} (target: {info.required_version or 'latest'})?"
            if info.status == DepStatus.NOT_INSTALLED
            else f"Upgrade {info.name} ({info.installed_version} -> {info.required_version or info.latest_version})?"
        )

        if not yes and not cfg_graphviz.dry_run and not typer.confirm(prompt_text, default=True):
            console.print(f"[yellow]Skipping {info.name}.[/yellow]\n")
            continue

        execute_dependency_install(
            info, None, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv
        )


# Typer Application
app = typer.Typer(
    name=Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-deps",
    help="Manages project system dependencies (Graphviz, PlantUML, JDK, Enchant, and UV).",
    no_args_is_help=False,
    add_completion=False,
)


def cli_version_callback(value: bool) -> None:
    """Print version string and exit."""
    if value:
        root = find_project_root()
        ver = get_project_version(root)
        console.print(f"install_deps.py (cs1302-book {ver})")
        raise typer.Exit(0)


@app.callback(invoke_without_command=True)
def cli_callback(
    ctx: typer.Context,
    _version: Annotated[
        bool | None,
        typer.Option(
            "-V",
            "--version",
            callback=cli_version_callback,
            is_eager=True,
            help="Display script and project version and exit",
        ),
    ] = None,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Main CLI handler for system dependencies manager."""
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    ctx.obj = (cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv)

    if ctx.invoked_subcommand is None:
        root = find_project_root()
        with err_console.status(
            "[bold cyan]Checking status of system dependencies...[/bold cyan]",
            spinner="dots",
        ):
            infos = collect_all_dependencies_status(
                root, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv
            )
        render_dependencies_table(infos)
        run_interactive_install(
            infos, force, yes, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv
        )


@app.command("status", help="Display status table for system dependencies.")
@app.command("check", hidden=True)
def cmd_status(
    deps: Annotated[
        list[str] | None,
        typer.Argument(
            help="Optional specific dependencies to check (enchant, graphviz, plantuml, jdk, uv, all)",
        ),
    ] = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Display status table for system dependencies."""
    cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv = (
        ctx.obj
        if ctx and ctx.obj
        else (
            graphviz.create_default_config(),
            plantuml.create_default_config(),
            jdk.create_default_config(),
            enchant.create_default_config(),
            uv.create_default_config(),
        )
    )
    root = find_project_root()
    with err_console.status(
        "[bold cyan]Checking status of system dependencies...[/bold cyan]",
        spinner="dots",
    ):
        infos = collect_all_dependencies_status(
            root, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv, deps
        )
    render_dependencies_table(infos)


@app.command("install", help="Check and interactively install/upgrade system dependencies.")
def cmd_install(
    deps: Annotated[
        list[str] | None,
        typer.Argument(
            help="Specific dependencies to install (enchant, graphviz, plantuml, jdk, uv, all)",
        ),
    ] = None,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Check and interactively install/upgrade system dependencies."""
    _ = ctx
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    root = find_project_root()
    with err_console.status(
        "[bold cyan]Checking status of system dependencies...[/bold cyan]",
        spinner="dots",
    ):
        infos = collect_all_dependencies_status(
            root, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv, deps
        )
    render_dependencies_table(infos)
    run_interactive_install(
        infos, force, yes, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv
    )


@app.command("update", help="Update all (or selected) system dependencies to latest versions.")
def cmd_update(
    deps: Annotated[
        list[str] | None,
        typer.Argument(
            help="Specific dependencies to update (enchant, graphviz, plantuml, jdk, uv, all)",
        ),
    ] = None,
    force: OptForce = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Update all (or selected) system dependencies to latest versions."""
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    root = find_project_root()
    with err_console.status(
        "[bold cyan]Checking for upstream updates...[/bold cyan]",
        spinner="dots",
    ):
        infos = collect_all_dependencies_status(
            root, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv, deps
        )
    render_dependencies_table(infos)

    for info in infos:
        latest = info.latest_version or "latest"
        prompt_text = f"Update {info.name} from {info.installed_version or 'none'} to {latest}?"
        if not yes and not dry_run and not typer.confirm(prompt_text, default=True):
            console.print(f"[yellow]Skipping {info.name}.[/yellow]\n")
            continue
        execute_dependency_install(
            info, latest, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv
        )


@app.command("clean", help="Remove unlinked cached downloads for all dependencies.")
@app.command("prune", hidden=True)
def cmd_clean(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Remove unlinked cached downloads for all dependencies."""
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    console.print("[bold]Cleaning Graphviz cache...[/bold]")
    _ = graphviz.clean_cache(cfg_graphviz)
    console.print("[bold]Cleaning PlantUML cache...[/bold]")
    _ = plantuml.clean_cache(cfg_plantuml)
    console.print("[bold]Cleaning JDK cache...[/bold]")
    _ = jdk.clean_cache(cfg_jdk)
    console.print("[bold]Cleaning Enchant cache...[/bold]")
    _ = enchant.clean_cache(cfg_enchant)
    console.print("[bold]Cleaning UV cache...[/bold]")
    _ = uv.clean_cache(cfg_uv)


@app.command("uninstall", help="Uninstall all (or selected) system dependencies.")
def cmd_uninstall(
    deps: Annotated[
        list[str] | None,
        typer.Argument(
            help="Specific dependencies to uninstall (enchant, graphviz, plantuml, jdk, uv, all)",
        ),
    ] = None,
    purge: OptPurge = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Uninstall all (or selected) system dependencies."""
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
    )
    root = find_project_root()
    infos = collect_all_dependencies_status(
        root, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv, deps
    )

    for info in infos:
        prompt_text = (
            f"Uninstall {info.name} and remove all cached archives?"
            if purge
            else f"Uninstall {info.name} (remove launchers and active links)?"
        )
        if not yes and not dry_run and not typer.confirm(prompt_text, default=True):
            console.print(f"[yellow]Skipping {info.name}.[/yellow]\n")
            continue

        if info.name == "graphviz":
            console.print("[bold]Uninstalling Graphviz...[/bold]")
            _ = graphviz.uninstall_graphviz(cfg_graphviz, purge=purge)
            console.print("[bold green]Graphviz uninstalled.[/bold green]\n")
        elif info.name == "plantuml":
            console.print("[bold]Uninstalling PlantUML...[/bold]")
            _ = plantuml.uninstall_plantuml(cfg_plantuml, purge=purge)
            console.print("[bold green]PlantUML uninstalled.[/bold green]\n")
        elif info.name == "enchant":
            console.print("[bold]Uninstalling Enchant...[/bold]")
            _ = enchant.uninstall_enchant(cfg_enchant, purge=purge)
            console.print("[bold green]Enchant uninstalled.[/bold green]\n")
        elif info.name == "uv":
            console.print("[bold]Uninstalling UV...[/bold]")
            _ = uv.uninstall_uv(cfg_uv, purge=purge)
            console.print("[bold green]UV uninstalled.[/bold green]\n")
        elif info.name in ("jdk", "java"):
            console.print("[bold]Uninstalling JDK...[/bold]")
            _ = jdk.uninstall_jdk(cfg_jdk, purge=purge)
            console.print("[bold green]JDK uninstalled.[/bold green]\n")


@app.command("which", help="Display paths and PATH status for dependency launchers.")
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Display paths and PATH status for dependency launchers."""
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
    )
    graphviz.render_which(cfg_graphviz)
    console.print()
    plantuml.render_which(cfg_plantuml)
    console.print()
    jdk.render_which(cfg_jdk)
    console.print()
    enchant.render_which(cfg_enchant)
    console.print()
    uv.render_which(cfg_uv)


@app.command(
    "rehash", help="Clear and regenerate shims in scripts/installer/shims/bin (or custom bin-dir)."
)
def cmd_rehash(
    deps: Annotated[
        list[str] | None,
        typer.Argument(
            help="Specific dependencies to rehash (enchant, graphviz, plantuml, jdk, uv, all)",
        ),
    ] = None,
    all_missing: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Install any missing dependencies before rehashing",
        ),
    ] = False,
    force: OptForce = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Clear and rebuild executable shims for system dependencies."""
    root = find_project_root()
    target_bin = bin_dir or resolve_shims_bin_dir(root)
    target_man = man_dir or resolve_shims_man_dir(root)
    cfg_graphviz = graphviz.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
        man_dir=target_man,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )
    cfg_plantuml = plantuml.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )
    cfg_jdk = jdk.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )
    cfg_enchant = enchant.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
        man_dir=target_man,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )
    cfg_uv = uv.create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
        man_dir=target_man,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )

    if all_missing:
        infos = collect_all_dependencies_status(
            root, cfg_graphviz, cfg_plantuml, cfg_jdk, cfg_enchant, cfg_uv, deps
        )
        run_interactive_install(
            infos,
            force=force,
            yes=True,
            cfg_graphviz=cfg_graphviz,
            cfg_plantuml=cfg_plantuml,
            cfg_jdk=cfg_jdk,
            cfg_enchant=cfg_enchant,
            cfg_uv=cfg_uv,
        )

    selected = [d.lower() for d in (deps or ["all"])]
    do_all = "all" in selected

    if do_all or "graphviz" in selected:
        graphviz.cmd_rehash(
            verbose=verbose,
            dry_run=dry_run,
            dir_path=dir_path,
            cache_dir=cache_dir,
            bin_dir=target_bin,
            man_dir=target_man,
        )
    if do_all or "plantuml" in selected:
        plantuml.cmd_rehash(
            verbose=verbose,
            dry_run=dry_run,
            dir_path=dir_path,
            cache_dir=cache_dir,
            bin_dir=target_bin,
        )
    if do_all or "jdk" in selected or "java" in selected:
        jdk.cmd_rehash(
            verbose=verbose,
            dry_run=dry_run,
            dir_path=dir_path,
            cache_dir=cache_dir,
            bin_dir=target_bin,
        )
    if do_all or "enchant" in selected:
        enchant.cmd_rehash(
            verbose=verbose,
            dry_run=dry_run,
            dir_path=dir_path,
            cache_dir=cache_dir,
            bin_dir=target_bin,
            man_dir=target_man,
        )
    if do_all or "uv" in selected:
        uv.cmd_rehash(
            verbose=verbose,
            dry_run=dry_run,
            dir_path=dir_path,
            cache_dir=cache_dir,
            bin_dir=target_bin,
            man_dir=target_man,
        )


@app.command("help", help="Display help information for dependency installer.")
def cmd_help(
    command_name: Annotated[
        str | None,
        typer.Argument(
            metavar="COMMAND",
            help="The command to display help information for.",
        ),
    ] = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Display help information for dependency installer or a specific command."""
    cli_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-deps"
    render_help(app, command_name, ctx, cli_name)


# Subcommand group: self
self_app = typer.Typer(
    name="self",
    help="Manage or inspect the installer script itself.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(self_app)


@self_app.command("version", help="Display script and project version.")
def cmd_self_version(
    short: OptShort = False,
) -> None:
    """Display script and project version."""
    root = find_project_root()
    ver = get_project_version(root)
    if short:
        console.print(ver)
    else:
        console.print(f"install_deps.py (cs1302-book {ver})")


@self_app.command("path", help="Display the path of this script.")
@self_app.command("which", hidden=True)
def cmd_self_path() -> None:
    """Display the path of this script."""
    console.print(Path(__file__).resolve())


def main() -> None:
    """Main CLI entry point for the script."""
    try:
        app()
    except Exception as e:  # noqa: BLE001
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1) from None


if __name__ == "__main__":  # pragma: no cover
    main()
