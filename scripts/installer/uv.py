# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "packaging>=24.2",
#     "requests>=2.32.3",
#     "rich>=13.9.4",
#     "typer>=0.15.1",
# ]
# ///
"""UV standalone installer and version manager.

Manages caching, version switching, launcher shims, and verification of Astral UV.
Downloads official pre-compiled releases from GitHub, manages isolated version
directories, and creates launcher shims for uv and uvx.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import requests
import typer
from rich.console import Console
from rich.table import Table

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
    format_path_for_display,
    get_min_system_dependency_version,
    get_project_version,
    is_version_ge,
    render_help,
)
from scripts.installer.common import (
    download_file as common_download_file,
)
from scripts.installer.graphviz import OptManDir

console = Console()
err_console = Console(stderr=True)

GITHUB_API_URL = "https://api.github.com/repos/astral-sh/uv/releases"
DEFAULT_FALLBACK_VERSION = "0.12.5"
SHIM_NAMES = ["uv", "uvx"]


@dataclass
class Config:
    """Configuration options for UV installer.

    Attributes:
        install_dir: Path where active versions and symlinks are managed.
        cache_dir: Path where release archives and unpacked builds reside.
        bin_dir: Path where executable launcher shims are created.
        man_dir: Path where man pages are linked (if any).
        verbose: Whether verbose diagnostics should be printed.
        dry_run: Whether execution should be simulated without disk changes.
        force: Whether to overwrite existing files and cache.
        yes: Whether interactive confirmation prompts should be auto-approved.
    """

    install_dir: Path
    cache_dir: Path
    bin_dir: Path
    man_dir: Path
    verbose: bool = False
    dry_run: bool = False
    force: bool = False
    yes: bool = False

    @property
    def current_link(self) -> Path:
        """Path to current version symlink."""
        return self.install_dir / "current"

    @property
    def primary_executable(self) -> Path:
        """Path to primary launcher shim."""
        return self.bin_dir / "uv"

    def log(self, message: str) -> None:
        """Log diagnostic message if verbose mode is enabled."""
        if self.verbose:
            err_console.print(f"[dim]{message}[/dim]")


def resolve_default_paths(project_root: Path) -> tuple[Path, Path, Path, Path]:
    """Resolve default directory locations for uv installations.

    Args:
        project_root: Root directory of the repository.

    Returns:
        Tuple of (install_dir, cache_dir, bin_dir, man_dir).
    """
    cache_dir = project_root / "scripts" / "cache" / "uv"
    install_dir = cache_dir

    venv_dir = project_root / ".venv"
    if venv_dir.is_dir() and (venv_dir / "bin").is_dir():
        bin_dir = venv_dir / "bin"
        man_dir = venv_dir / "share" / "man"
    else:
        bin_dir = project_root / "scripts" / "installer" / "shims" / "bin"
        man_dir = project_root / "scripts" / "installer" / "shims" / "share" / "man"

    return install_dir, cache_dir, bin_dir, man_dir


def create_default_config(
    dir_path: Path | None = None,
    cache_dir: Path | None = None,
    bin_dir: Path | None = None,
    man_dir: Path | None = None,
    verbose: bool = False,
    dry_run: bool = False,
    force: bool = False,
    yes: bool = False,
) -> Config:
    """Construct Config with environment and flag overrides.

    Args:
        dir_path: Explicit base install directory override.
        cache_dir: Explicit cache directory override.
        bin_dir: Explicit bin directory override for shims.
        man_dir: Explicit man directory override.
        verbose: Enable verbose logging.
        dry_run: Simulate changes without disk modifications.
        force: Force re-download and re-link.
        yes: Auto-confirm prompts.

    Returns:
        Instantiated Config object.
    """
    root = find_project_root()
    d_install, d_cache, d_bin, d_man = resolve_default_paths(root)

    env_install = os.environ.get("UV_INSTALL_DIR")
    env_cache = os.environ.get("UV_CACHE_DIR")
    env_bin = os.environ.get("UV_BIN_DIR")
    env_man = os.environ.get("UV_MAN_DIR")
    env_verbose = os.environ.get("VERBOSE", "").lower() in ("1", "true", "yes")

    final_install = dir_path or (Path(env_install) if env_install else d_install)
    final_cache = cache_dir or (Path(env_cache) if env_cache else d_cache)
    final_bin = bin_dir or (Path(env_bin) if env_bin else d_bin)
    final_man = man_dir or (Path(env_man) if env_man else d_man)

    return Config(
        install_dir=final_install,
        cache_dir=final_cache,
        bin_dir=final_bin,
        man_dir=final_man,
        verbose=verbose or env_verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )


def get_min_uv_version(project_root: Path) -> str | None:
    """Read minimum required uv version from pyproject.toml.

    Args:
        project_root: Root directory of repository.

    Returns:
        Version string or None if unconstrained.
    """
    return get_min_system_dependency_version(project_root, "uv")


def detect_platform_archive(version_tag: str) -> tuple[str, str]:
    """Determine target platform archive filename and format for Astral UV.

    Args:
        version_tag: Clean version tag string (e.g. '0.12.5').

    Returns:
        Tuple of (archive_filename, format_type). format_type is 'tar.gz' or 'zip'.
    """
    _ = version_tag
    sys_name = platform.system().lower()
    machine = platform.machine().lower()

    if sys_name == "darwin":
        if machine in ("arm64", "aarch64"):
            return "uv-aarch64-apple-darwin.tar.gz", "tar.gz"
        return "uv-x86_64-apple-darwin.tar.gz", "tar.gz"
    elif sys_name == "linux":
        if machine in ("arm64", "aarch64"):
            return "uv-aarch64-unknown-linux-gnu.tar.gz", "tar.gz"
        elif machine.startswith(("armv7", "armv6")):
            return "uv-armv7-unknown-linux-gnueabihf.tar.gz", "tar.gz"
        elif machine in ("i386", "i686"):
            return "uv-i686-unknown-linux-gnu.tar.gz", "tar.gz"
        else:
            return "uv-x86_64-unknown-linux-gnu.tar.gz", "tar.gz"
    elif sys_name == "windows":
        if machine in ("arm64", "aarch64"):
            return "uv-aarch64-pc-windows-msvc.zip", "zip"
        return "uv-x86_64-pc-windows-msvc.zip", "zip"
    else:
        return "uv-x86_64-unknown-linux-musl.tar.gz", "tar.gz"


def get_installed_version(target_path: Path | None) -> str | None:
    """Detect version of uv installed at target_path or in active environment.

    Args:
        target_path: Directory, binary path, or symlink to inspect.

    Returns:
        Version string (e.g. '0.12.5') or None if not found.
    """
    if target_path is None or not target_path.exists():
        return None

    exec_bin = None
    if target_path.is_file() and os.access(target_path, os.X_OK):
        exec_bin = target_path
    elif target_path.is_dir():
        candidates = [
            target_path / "bin" / "uv",
            target_path / "uv",
            target_path / "uv.exe",
            target_path / "bin" / "uv.exe",
        ]
        for cand in candidates:
            if cand.is_file() and os.access(cand, os.X_OK):
                exec_bin = cand
                break

    if not exec_bin:
        resolved_dir = target_path.resolve() if target_path.is_symlink() else target_path
        match_dir = re.search(r"(\d+\.\d+(?:\.\d+)?)", resolved_dir.name)
        if match_dir:
            return match_dir.group(1)
        return None

    try:
        res = subprocess.run(
            [str(exec_bin), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = res.stdout or res.stderr
        if out:
            match = re.search(r"uv\s+(\d+\.\d+(?:\.\d+)?)", out, re.IGNORECASE)
            if not match:
                match = re.search(r"(\d+\.\d+(?:\.\d+)?)", out)
            if match:
                return match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass

    resolved_dir = target_path.resolve() if target_path.is_symlink() else target_path
    match_dir = re.search(r"(\d+\.\d+(?:\.\d+)?)", resolved_dir.name)
    if match_dir:
        return match_dir.group(1)

    return None


def get_latest_github_version() -> str:
    """Fetch the latest release version of UV from GitHub.

    Returns:
        Latest release version tag string.
    """
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "cs1302-installer/uv"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(f"{GITHUB_API_URL}/latest", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            tag = data.get("tag_name", "").lstrip("v")
            if tag:
                return tag
        elif resp.status_code == 404:
            # Fallback to list endpoint
            resp_all = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            if resp_all.status_code == 200:
                for release in resp_all.json():
                    if not release.get("prerelease") and not release.get("draft"):
                        tag = release.get("tag_name", "").lstrip("v")
                        if tag:
                            return tag
    except (requests.RequestException, ValueError):
        pass

    return DEFAULT_FALLBACK_VERSION


def get_github_release_versions() -> list[str]:
    """Fetch available UV release version tags from GitHub.

    Returns:
        List of release version strings.
    """
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "cs1302-installer/uv"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    versions: list[str] = []
    try:
        resp = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
        if resp.status_code == 200:
            for release in resp.json():
                if not release.get("prerelease") and not release.get("draft"):
                    tag = release.get("tag_name", "").lstrip("v")
                    if tag and tag not in versions:
                        versions.append(tag)
    except (requests.RequestException, ValueError):
        pass

    if not versions:
        versions.append(DEFAULT_FALLBACK_VERSION)
    return versions


def resolve_target_tag(version: str, cfg: Config) -> tuple[str, str]:
    """Resolve requested version keyword to explicit version string and asset URL.

    Args:
        version: Version keyword ('latest') or specific version ('0.12.5').
        cfg: Runtime configuration.

    Returns:
        Tuple of (clean_version_tag, download_url).
    """
    if version.lower() == "latest":
        tag = get_latest_github_version()
        cfg.log(f"Resolved 'latest' -> UV {tag}")
    else:
        tag = version.lstrip("v")

    archive_name, _ = detect_platform_archive(tag)
    url = f"https://github.com/astral-sh/uv/releases/download/{tag}/{archive_name}"
    return tag, url


def download_and_extract_uv(version: str, cfg: Config) -> Path:
    """Download, cache, and unpack UV binaries.

    Args:
        version: Target version string.
        cfg: Runtime configuration.

    Returns:
        Path to unpacked version directory.
    """
    tag, download_url = resolve_target_tag(version, cfg)
    target_version_dir = cfg.cache_dir / tag
    archive_name, archive_format = detect_platform_archive(tag)
    archive_path = cfg.cache_dir / archive_name

    if target_version_dir.is_dir() and not cfg.force:
        installed_ver = get_installed_version(target_version_dir)
        if installed_ver:
            cfg.log(f"UV {tag} already installed in {target_version_dir}")
            return target_version_dir

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would download {download_url} to {format_path_for_display(archive_path)}[/yellow]"
        )
        console.print(
            f"[yellow]\\[dry-run] Would extract to {format_path_for_display(target_version_dir)}[/yellow]"
        )
        return target_version_dir

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    if not archive_path.is_file() or cfg.force:
        success = common_download_file(
            url=download_url,
            dest_path=archive_path,
            description=f"UV v{tag} ({archive_name})",
            dry_run=cfg.dry_run,
        )
        if not success:
            err_console.print(f"[red]error:[/red] Failed to download {download_url}")
            raise typer.Exit(1)

    with err_console.status(f"[bold cyan]Extracting UV v{tag}...[/bold cyan]", spinner="dots"):
        if target_version_dir.exists():
            shutil.rmtree(target_version_dir, ignore_errors=True)
        target_version_dir.mkdir(parents=True, exist_ok=True)

        if archive_format == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(target_version_dir)
        else:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(target_version_dir)

        # Move nested extracted directory contents up if extracted in a subdirectory
        children = list(target_version_dir.iterdir())
        if len(children) == 1 and children[0].is_dir():
            inner_dir = children[0]
            for item in inner_dir.iterdir():
                _ = shutil.move(str(item), str(target_version_dir / item.name))
            inner_dir.rmdir()

        # Ensure binaries have executable permissions
        bin_dir = target_version_dir / "bin"
        for search_dir in (target_version_dir, bin_dir):
            if search_dir.is_dir():
                for binary_name in SHIM_NAMES:
                    bin_file = search_dir / binary_name
                    if bin_file.is_file():
                        bin_file.chmod(bin_file.stat().st_mode | 0o755)

    return target_version_dir


def create_launcher_shims(version_dir: Path, cfg: Config) -> list[Path]:
    """Create executable launcher shims for uv and uvx.

    Args:
        version_dir: Version installation directory containing binaries.
        cfg: Runtime configuration.

    Returns:
        List of created shim file paths.
    """
    created_shims: list[Path] = []
    if cfg.dry_run:
        for shim in SHIM_NAMES:
            shim_path = cfg.bin_dir / shim
            console.print(
                f"  [yellow]\\[dry-run] Would create launcher shim {format_path_for_display(shim_path)}[/yellow]"
            )
            created_shims.append(shim_path)
        return created_shims

    cfg.bin_dir.mkdir(parents=True, exist_ok=True)
    target_bin = version_dir / "bin" if (version_dir / "bin").is_dir() else version_dir

    for shim in SHIM_NAMES:
        target_binary = target_bin / shim
        if not target_binary.is_file():
            # Check for Windows extension or fallback
            target_binary = target_bin / f"{shim}.exe"

        shim_path = cfg.bin_dir / shim
        script_content = f"""#!/bin/sh
# CS1302 UV Launcher Shim
UV_DIR="{version_dir.resolve()}"
UV_BIN="{target_binary.resolve()}"

if [ ! -f "$UV_BIN" ]; then
    echo "error: UV binary not found at $UV_BIN" >&2
    exit 1
fi

exec "$UV_BIN" "$@"
"""
        _ = shim_path.write_text(script_content, encoding="utf-8")
        shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        created_shims.append(shim_path)

    return created_shims


def apply_version_link(version: str, cfg: Config) -> None:
    """Install and activate a UV version, linking shims to the environment.

    Args:
        version: Target version tag.
        cfg: Runtime configuration.
    """
    tag, _ = resolve_target_tag(version, cfg)
    version_dir = download_and_extract_uv(tag, cfg)

    if (
        not cfg.yes
        and not cfg.dry_run
        and not typer.confirm(f"Install and activate UV {tag}?", default=True)
    ):
        console.print("[yellow]Installation aborted.[/yellow]")
        raise typer.Exit(0)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would symlink {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}[/yellow]"
        )
        _ = create_launcher_shims(version_dir, cfg)
        return

    cfg.install_dir.mkdir(parents=True, exist_ok=True)

    if cfg.current_link.is_symlink() or cfg.current_link.is_file():
        cfg.current_link.unlink()
    elif cfg.current_link.is_dir():
        shutil.rmtree(cfg.current_link)

    cfg.current_link.symlink_to(version_dir.resolve())
    created_shims = create_launcher_shims(version_dir, cfg)

    console.print(f"\n[bold green]UV v{tag} successfully configured![/bold green]")
    console.print(f"  Installed Path: {format_path_for_display(version_dir)}")
    console.print(
        f"  Active Link:    {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}"
    )
    console.print(
        f"  Created Shims:  {len(created_shims)} binaries in {format_path_for_display(cfg.bin_dir)}"
    )

    current_path = os.environ.get("PATH", "").split(os.pathsep)
    if str(cfg.bin_dir.resolve()) not in [str(Path(p).resolve()) for p in current_path if p]:
        console.print("=" * 72, style="yellow")
        console.print(
            f"NOTE: '{format_path_for_display(cfg.bin_dir)}' is not in your current PATH.\n",
            style="bold yellow",
        )
        console.print("To use 'uv' directly from your terminal, add it to your PATH:\n")
        console.print(
            f'  export PATH="{format_path_for_display(cfg.bin_dir)}:$PATH"\n',
            style="bold green",
        )
        console.print("=" * 72, style="yellow")


def render_versions_table(cfg: Config) -> None:
    """Display table of all cached UV versions.

    Args:
        cfg: Runtime configuration.
    """
    table = Table(title="Cached UV Installations")
    table.add_column("Version", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Active", justify="center")

    active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None

    found = 0
    if cfg.cache_dir.is_dir():
        for entry in sorted(cfg.cache_dir.iterdir()):
            if entry.is_dir() and entry.name != "current":
                ver = get_installed_version(entry)
                is_active = active_target is not None and entry.resolve() == active_target
                active_str = "[bold green]✓ active[/bold green]" if is_active else ""
                table.add_row(ver or entry.name, format_path_for_display(entry), active_str)
                found += 1

    if found == 0:
        console.print("[yellow]No cached UV versions found.[/yellow]")
    else:
        console.print(table)


def render_status(cfg: Config) -> None:
    """Display comprehensive status of active UV installation.

    Args:
        cfg: Runtime configuration.
    """
    with err_console.status("[bold cyan]Inspecting UV installation...[/bold cyan]"):
        active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None
        active_ver = get_installed_version(cfg.current_link) if cfg.current_link.exists() else None
        latest_ver = get_latest_github_version()
        min_ver = get_min_uv_version(find_project_root())

    console.print("[bold]UV Installation Status:[/bold]")
    console.print(f"  Active version:       [cyan]{active_ver or 'none (not installed)'}[/cyan]")
    console.print(f"  Latest GitHub tag:    [green]{latest_ver}[/green]")
    if min_ver:
        console.print(f"  Project min version:  {min_ver}")
    console.print(f"  Installed location:   {format_path_for_display(active_target)}")
    console.print(f"  Shims directory:      {format_path_for_display(cfg.bin_dir)}")

    if not active_ver:
        console.print(
            "\n[bold yellow]Status: UV is not installed. Run 'install-uv install' to install.[/bold yellow]"
        )
    elif min_ver and not is_version_ge(active_ver, min_ver):
        console.print(
            f"\n[bold red]Status: Active version ({active_ver}) does not satisfy project minimum requirement ({min_ver}). "
            + f"Run 'install-uv install {min_ver}' to upgrade.[/bold red]"
        )
    else:
        console.print("\n[bold green]Status: UV is up to date.[/bold green]")


def clean_cache(cfg: Config) -> int:
    """Remove cached UV versions that are not currently active.

    Args:
        cfg: Runtime configuration.

    Returns:
        Number of removed directories and archives.
    """
    active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None
    removed = 0

    if cfg.cache_dir.is_dir():
        for entry in cfg.cache_dir.iterdir():
            if entry.name == "current":
                continue
            if entry.is_dir() and active_target and (entry.resolve() == active_target):
                continue
            if cfg.dry_run:
                console.print(
                    f"  [yellow]\\[dry-run] Would remove {format_path_for_display(entry)}[/yellow]"
                )
            else:
                console.print(f"  Removing {format_path_for_display(entry)}")
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
            removed += 1

    return removed


def uninstall_uv(cfg: Config, purge: bool = False) -> tuple[list[Path], Path | None, list[Path]]:
    """Remove UV launcher shims and current active link.

    Args:
        cfg: Runtime configuration.
        purge: Whether to remove all cached versions and downloads.

    Returns:
        Tuple of (removed_shims, removed_link, removed_cache_entries).
    """
    removed_shims: list[Path] = []
    removed_link: Path | None = None
    removed_cache: list[Path] = []

    for shim in SHIM_NAMES:
        shim_path = cfg.bin_dir / shim
        if shim_path.is_file() or shim_path.is_symlink():
            if not cfg.dry_run:
                shim_path.unlink(missing_ok=True)
            removed_shims.append(shim_path)

    if cfg.current_link.is_symlink() or cfg.current_link.is_file():
        if not cfg.dry_run:
            cfg.current_link.unlink()
        removed_link = cfg.current_link
    elif cfg.current_link.is_dir():
        if not cfg.dry_run:
            shutil.rmtree(cfg.current_link)
        removed_link = cfg.current_link

    if purge and cfg.cache_dir.is_dir():
        for entry in cfg.cache_dir.iterdir():
            if not cfg.dry_run:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
            removed_cache.append(entry)

    return removed_shims, removed_link, removed_cache


def render_which(cfg: Config) -> None:
    """Display active UV binary location, symlink, and PATH status.

    Args:
        cfg: Runtime configuration.
    """
    active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None
    primary_bin = cfg.bin_dir / "uv"
    in_path = str(cfg.bin_dir.resolve()) in [
        str(Path(p).resolve()) for p in os.environ.get("PATH", "").split(os.pathsep) if p
    ]

    console.print("[bold]UV Locations:[/bold]")
    console.print(f"  Active Installation: {format_path_for_display(active_target)}")
    console.print(f"  Launcher Shim:       {format_path_for_display(primary_bin)}")
    console.print(
        f"  In current PATH:     {'[green]Yes[/green]' if in_path else '[yellow]No[/yellow]'}"
    )


def get_config_from_context(
    ctx: typer.Context | None,
    verbose: bool = False,
    dry_run: bool = False,
    force: bool = False,
    yes: bool = False,
    dir_path: Path | None = None,
    cache_dir: Path | None = None,
    bin_dir: Path | None = None,
    man_dir: Path | None = None,
) -> Config:
    """Extract or create Config object from Typer Context."""
    if ctx and ctx.obj and isinstance(ctx.obj, Config):
        cfg = ctx.obj
        if verbose:
            cfg.verbose = True
        if dry_run:
            cfg.dry_run = True
        if force:
            cfg.force = True
        if yes:
            cfg.yes = True
        if dir_path:
            cfg.install_dir = dir_path
        if cache_dir:
            cfg.cache_dir = cache_dir
        if bin_dir:
            cfg.bin_dir = bin_dir
        if man_dir:
            cfg.man_dir = man_dir
        return cfg

    cfg = create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    if ctx:
        ctx.obj = cfg
    return cfg


# Typer Application Setup
app = typer.Typer(
    name=Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-uv",
    help="Installer and version manager for Astral UV.",
    no_args_is_help=False,
    add_completion=False,
)

self_app = typer.Typer(
    name="self",
    help="Manage the installer script itself.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(self_app, name="self")


@app.callback(invoke_without_command=True)
def cli_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "-V",
            "--version",
            help="Display script and project version and exit",
            is_eager=True,
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
    """Main CLI option callback."""
    if version:
        root = find_project_root()
        ver = get_project_version(root)
        console.print(f"install-uv.py (cs1302-code-visualizer {ver})")
        raise typer.Exit(0)

    cfg = create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    if ctx:
        ctx.obj = cfg

    if ctx and ctx.invoked_subcommand is None:
        render_status(cfg)


@app.command("install", help="Download and configure specified (or latest) UV version.")
def cmd_install(
    version_tag: Annotated[
        str | None,
        typer.Argument(
            metavar="[VERSION]",
            help="Specific version tag (e.g. '0.12.5') or 'latest'",
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
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Download and configure specified (or latest) UV version."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    target = version_tag or get_min_uv_version(find_project_root()) or "latest"
    apply_version_link(target, cfg)


@app.command("update", help="Upgrade UV to the latest upstream release.")
def cmd_update(
    force: OptForce = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Check upstream for the latest UV release and upgrade."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    with err_console.status("[bold cyan]Checking upstream UV releases...[/bold cyan]"):
        latest = get_latest_github_version()
        current = get_installed_version(cfg.current_link)

    if current and is_version_ge(current, latest) and not cfg.force:
        console.print(f"[bold green]UV is already up to date ({current}).[/bold green]")
        return

    console.print(f"Upgrading UV: {current or 'none'} -> [bold cyan]{latest}[/bold cyan]")
    apply_version_link(latest, cfg)


@app.command("use", help="Switch active installation to VERSION.")
def cmd_use(
    version: Annotated[
        str,
        typer.Argument(
            metavar="VERSION",
            help="UV version to activate (e.g. '0.12.5')",
        ),
    ],
    force: OptForce = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Switch active installation to VERSION (downloads on demand)."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    apply_version_link(version, cfg)


@app.command("versions", help="List all cached UV versions.")
def cmd_versions(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """List all cached UV versions and mark active link."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    render_versions_table(cfg)


@app.command("status", help="Display current active UV version and paths.")
def cmd_status(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Display current active UV version and paths."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    render_status(cfg)


@app.command("clean", help="Remove cached UV versions that are not active.")
def cmd_clean(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Remove cached UV installations that are not active."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    if (
        not cfg.yes
        and not cfg.dry_run
        and not typer.confirm("Remove unused cached UV versions?", default=True)
    ):
        console.print("[yellow]Clean operation aborted.[/yellow]")
        raise typer.Exit(0)

    removed = clean_cache(cfg)
    if cfg.dry_run:
        console.print(f"[yellow]\\[dry-run] Would clean {removed} unused item(s).[/yellow]")
    else:
        console.print(f"[green]Successfully cleaned {removed} unused item(s).[/green]")


@app.command("uninstall", help="Remove UV launcher shims and active link.")
def cmd_uninstall(
    purge: OptPurge = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Uninstall UV by removing launcher shims and active link."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    prompt_msg = (
        "Uninstall UV and remove all cached downloads?"
        if purge
        else "Uninstall UV (remove launchers and active symlink)?"
    )
    if not cfg.yes and not cfg.dry_run and not typer.confirm(prompt_msg, default=True):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    removed_shims, removed_link, removed_cache = uninstall_uv(cfg, purge=purge)
    console.print(f"Removed {len(removed_shims)} launcher shim(s).")
    if removed_link:
        console.print(f"Removed active link: {format_path_for_display(removed_link)}")
    if purge:
        console.print(f"Removed {len(removed_cache)} cached item(s).")
    console.print("[bold green]UV successfully uninstalled.[/bold green]")


@app.command("which", help="Display active UV binary and shims location.")
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Display active UV binary and shims location."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    render_which(cfg)


@app.command("rehash", help="Regenerate launcher shims for active version.")
def cmd_rehash(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Regenerate launcher shims for active version."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    if not cfg.current_link.exists():
        console.print(
            "[yellow]No active UV installation linked. Run 'install-uv install' first.[/yellow]"
        )
        return

    active_dir = cfg.current_link.resolve()
    shims = create_launcher_shims(active_dir, cfg)
    console.print(
        f"[bold green]Rehashed {len(shims)} shims in {format_path_for_display(cfg.bin_dir)}[/bold green]"
    )


@app.command(
    "exec",
    help="Run a command with UV bin directory prepended to PATH.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_exec(
    ctx: typer.Context,
    use: Annotated[
        str | None,
        typer.Option(
            "--use",
            "--use-version",
            help="UV version to use for this execution.",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable verbose diagnostics")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what actions would be taken")
    ] = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
) -> None:
    """Run a command with UV bin directory prepended to PATH."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    raw_args: list[str] = []
    argv = sys.argv[1:]
    exec_idx = -1
    for i, a in enumerate(argv):
        if a in ("exec", "run"):
            exec_idx = i
            break

    use_val = use
    if exec_idx != -1:
        sub_args = argv[exec_idx + 1 :]
        i = 0
        while i < len(sub_args):
            arg = sub_args[i]
            if arg in ("--use", "--use-version") and i + 1 < len(sub_args):
                use_val = sub_args[i + 1]
                i += 2
            elif arg.startswith("--use="):
                use_val = arg.split("=", 1)[1]
                i += 1
            elif arg in ("-v", "--verbose", "-n", "--dry-run", "-f", "--force", "-y", "--yes"):
                i += 1
            else:
                raw_args.append(arg)
                i += 1

    cmd_args = raw_args or ctx.args
    if not cmd_args:
        err_console.print(
            "[red]error:[/red] 'exec' requires a command to execute (e.g. 'install-uv exec uv --version')"
        )
        raise typer.Exit(1)

    if use_val:
        version_dir = download_and_extract_uv(use_val, cfg)
    else:
        if not cfg.current_link.exists():
            version_dir = download_and_extract_uv("latest", cfg)
            apply_version_link("latest", cfg)
        else:
            version_dir = cfg.current_link.resolve()

    target_bin = version_dir / "bin" if (version_dir / "bin").is_dir() else version_dir
    new_env = os.environ.copy()
    new_env["PATH"] = f"{target_bin}{os.pathsep}{new_env.get('PATH', '')}"

    try:
        res = subprocess.run(cmd_args, env=new_env, check=False)
        sys.exit(res.returncode)
    except (OSError, subprocess.SubprocessError) as exc:
        err_console.print(f"[red]error:[/red] Failed to execute command: {exc}")
        sys.exit(1)


@app.command(
    "help",
    help="Display help information for UV installer or a specific command.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
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
    """Display help information for UV installer or a specific command."""
    cli_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-uv"
    render_help(app, command_name, ctx, cli_name)


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
        console.print(f"install-uv.py (cs1302-code-visualizer {ver})")


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
