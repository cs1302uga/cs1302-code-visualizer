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
"""PlantUML standalone JAR version and installation manager.

Downloads versioned PlantUML JARs into a cache directory and manages the active
version via an atomic symlink.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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
    clean_version_tag,
    find_project_root,
    format_path_for_display,
    get_min_system_dependency_version,
    get_project_version,
    is_version_ge,
    render_help,
    resolve_default_bin_dir,
    resolve_shims_bin_dir,
)
from scripts.installer.common import (
    download_file as common_download_file,
)

console = Console()
err_console = Console(stderr=True)


def get_min_jar_version(root_dir: Path) -> str | None:
    """Read minimum PlantUML version from pyproject.toml.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Configured minimum version string if present, else None.
    """
    return get_min_system_dependency_version(root_dir, "plantuml")


@dataclass
class Config:
    """Runtime configuration and filesystem locations.

    Attributes:
        install_dir: Directory containing the active symlink.
        cache_dir: Directory storing versioned JARs.
        bin_dir: Directory containing the launcher binary.
        verbose: Whether verbose logging is enabled.
        dry_run: Whether dry-run mode is active.
        force: Whether to force re-download / link overwrite.
        yes: Whether to automatically accept all interactive prompts.
    """

    install_dir: Path
    cache_dir: Path
    bin_dir: Path
    verbose: bool = False
    dry_run: bool = False
    force: bool = False
    yes: bool = False

    @property
    def jar_symlink(self) -> Path:
        """Path to the active plantuml.jar symlink."""
        return self.install_dir / "plantuml.jar"

    @property
    def wrapper_path(self) -> Path:
        """Path to the executable plantuml launcher."""
        return self.bin_dir / "plantuml"

    def log(self, message: str) -> None:
        """Print verbose log if enabled.

        Args:
            message: Message to log to standard error.
        """
        if self.verbose:
            err_console.print(f"[dim][install_plantuml.py][/dim] {message}")


def resolve_default_paths(root_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """Resolve default directories based on the project root directory.

    Args:
        root_dir: Optional root directory of the project.

    Returns:
        A tuple of (default_install_dir, default_cache_dir, default_bin_dir).
    """
    root = root_dir or find_project_root()
    default_install_dir = root / "scripts" / "cache"
    default_cache_dir = root / "scripts" / "cache" / "plantuml"
    default_bin_dir = resolve_default_bin_dir(root)
    return default_install_dir, default_cache_dir, default_bin_dir


def create_default_config(
    dir_path: Path | None = None,
    cache_dir: Path | None = None,
    bin_dir: Path | None = None,
    verbose: bool = False,
    dry_run: bool = False,
    force: bool = False,
    yes: bool = False,
) -> Config:
    """Create a Config object with project defaults and CLI overrides.

    Args:
        dir_path: Custom install directory override.
        cache_dir: Custom cache directory override.
        bin_dir: Custom launcher binary directory override.
        verbose: Verbose output flag.
        dry_run: Dry-run execution flag.
        force: Force re-download / overwrite flag.
        yes: Automatic yes confirmation flag.

    Returns:
        Configured Config instance.
    """
    def_install, def_cache, def_bin = resolve_default_paths()
    env_verbose = os.environ.get("VERBOSE", "0") in ("1", "true", "True")
    return Config(
        install_dir=dir_path or def_install,
        cache_dir=cache_dir or def_cache,
        bin_dir=bin_dir or def_bin,
        verbose=verbose or env_verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
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
) -> Config:
    """Extract or build Config from Typer Context and command arguments.

    Args:
        ctx: Current Typer Context.
        verbose: Verbose flag override.
        dry_run: Dry-run flag override.
        force: Force flag override.
        yes: Automatic yes flag override.
        dir_path: Install dir override.
        cache_dir: Cache dir override.
        bin_dir: Bin dir override.

    Returns:
        Config instance with combined flags.
    """
    if ctx is not None and getattr(ctx, "obj", None) is not None and isinstance(ctx.obj, Config):
        cfg = ctx.obj
        return Config(
            install_dir=dir_path or cfg.install_dir,
            cache_dir=cache_dir or cfg.cache_dir,
            bin_dir=bin_dir or cfg.bin_dir,
            verbose=verbose or cfg.verbose,
            dry_run=dry_run or cfg.dry_run,
            force=force or cfg.force,
            yes=yes or cfg.yes,
        )
    return create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )


def get_active_target(symlink_path: Path) -> Path | None:
    """Safely resolve the target Path of a symlink if it exists.

    Args:
        symlink_path: Path to the symlink to inspect.

    Returns:
        The target Path if valid, otherwise None.
    """
    try:
        if symlink_path.is_symlink():
            return symlink_path.resolve()
        if symlink_path.exists():
            return symlink_path
    except OSError:  # pragma: no cover
        pass
    return None


def get_installed_version(target: Path | None) -> str | None:
    """Extract semantic version number from target JAR filename.

    Args:
        target: Target Path to a plantuml-<version>.jar.

    Returns:
        Version string (e.g. '1.2026.6') or None if uninstalled.
    """
    active = get_active_target(target) if target else None
    if not active:
        return None
    name = active.name
    if name.startswith("plantuml-") and name.endswith(".jar"):
        ver = name[len("plantuml-") : -len(".jar")]
        return clean_version_tag(ver)
    return None


def get_github_releases(cfg: Config | None = None) -> list[dict]:
    """Fetch releases from GitHub API.

    Args:
        cfg: Optional runtime configuration.

    Returns:
        List of release dicts from GitHub API.
    """
    url = "https://api.github.com/repos/plantuml/plantuml/releases"
    if cfg:
        cfg.log(f"Fetching releases from {url}")
    try:
        resp = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "cs1302-book-plantuml-installer/1.0",
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
        if cfg:
            cfg.log(f"GitHub API returned status code {resp.status_code}")
    except (requests.RequestException, ValueError) as e:
        if cfg:
            cfg.log(f"GitHub API error: {e}")
    return []


def get_latest_github_version() -> str | None:
    """Fetch the latest release tag from GitHub API.

    Returns:
        Latest release tag string (e.g. '1.2026.6'), or None on failure.
    """
    url = "https://api.github.com/repos/plantuml/plantuml/releases/latest"
    try:
        resp = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "cs1302-book-plantuml-installer/1.0",
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "tag_name" in data:
                return clean_version_tag(str(data["tag_name"]))
    except (requests.RequestException, ValueError):
        pass
    return None


def download_and_cache_version(tag: str, cfg: Config) -> Path:
    """Download a specific PlantUML JAR version into cache directory.

    Args:
        tag: Version string (e.g. '1.2026.6' or 'v1.2026.6') or 'latest'.
        cfg: Runtime configuration.

    Returns:
        Path to the downloaded JAR in cache.
    """
    clean_tag = clean_version_tag(tag)
    if clean_tag.lower() == "latest":
        latest = get_latest_github_version()
        if latest:
            clean_tag = latest
        else:
            clean_tag = "1.2026.6"

    raw_tag = f"v{clean_tag}"
    jar_name = f"plantuml-{clean_tag}.jar"
    target_jar = cfg.cache_dir / jar_name

    if not cfg.force and target_jar.exists():
        cfg.log(f"Using existing cached JAR: {target_jar}")
        return target_jar

    url = f"https://github.com/plantuml/plantuml/releases/download/{raw_tag}/{jar_name}"
    fallback_url = f"https://github.com/plantuml/plantuml/releases/download/{raw_tag}/plantuml.jar"

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    success = common_download_file(
        url=url,
        dest_path=target_jar,
        description=f"Downloading PlantUML v{clean_tag}",
        dry_run=cfg.dry_run,
        verbose=cfg.verbose,
    )

    if not success and not cfg.dry_run:
        cfg.log(f"Primary URL failed, attempting fallback URL: {fallback_url}")
        success = common_download_file(
            url=fallback_url,
            dest_path=target_jar,
            description=f"Downloading PlantUML v{clean_tag} (fallback)",
            dry_run=cfg.dry_run,
            verbose=cfg.verbose,
        )

    if not success and not cfg.dry_run:
        err_console.print(
            f"[red]error:[/red] Failed to download PlantUML release '{tag}' from GitHub."
        )
        raise typer.Exit(1)

    return target_jar


def create_launcher(jar_path: Path, bin_dir: Path, cfg: Config) -> Path:
    """Generate shell launcher wrapper script in bin_dir.

    Args:
        jar_path: Path to target active plantuml.jar symlink.
        bin_dir: Directory to place the executable launcher wrapper in.
        cfg: Runtime configuration.

    Returns:
        Path to the generated wrapper script.
    """
    wrapper = bin_dir / "plantuml"
    if cfg.dry_run:
        return wrapper

    bin_dir.mkdir(parents=True, exist_ok=True)
    jar_target = str(jar_path.resolve() if jar_path.is_symlink() else jar_path)

    content = f"""#!/usr/bin/env bash
#
# PlantUML launcher wrapper generated by install_plantuml.py
#
set -euo pipefail

JAR_PATH="{jar_path}"

if [[ ! -f "${{JAR_PATH}}" ]]; then
    if [[ -f "{jar_target}" ]]; then
        JAR_PATH="{jar_target}"
    else
        printf "error: PlantUML JAR not found at %s. Please run install_plantuml.py to reinstall.\\n" "${{JAR_PATH}}" >&2
        exit 1
    fi
fi

if [[ "${{CHECK_UPDATE:-0}}" == "1" ]]; then
    if command -v curl >/dev/null 2>&1; then
        LATEST="$(curl -s https://api.github.com/repos/plantuml/plantuml/releases/latest | grep '"tag_name":' | sed -E 's/.*"v?([^"]+)".*/\\1/' || true)"
        if [[ -n "${{LATEST}}" ]]; then
            CURRENT="$(java -jar "${{JAR_PATH}}" -version 2>/dev/null | grep -Eo 'version [0-9.]+' | head -n 1 | awk '{{print $2}}' || true)"
            if [[ -n "${{CURRENT}}" && "${{CURRENT}}" != "${{LATEST}}" ]]; then
                LOWEST="$(printf "%s\\n%s\\n" "${{CURRENT}}" "${{LATEST}}" | sort -V | head -n 1)"
                if [[ "${{LOWEST}}" == "${{CURRENT}}" ]]; then
                    printf "\\n[plantuml] A newer version of PlantUML (%s) is available. Run 'scripts/installer/plantuml.py update' to upgrade.\\n\\n" "${{LATEST}}" >&2
                fi
            fi
        fi
    fi
fi

exec java -jar "${{JAR_PATH}}" "$@"
"""
    wrapper.write_text(content, encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def apply_version_link(
    tag: str,
    cfg: Config,
    is_explicit_use: bool = False,
) -> Path:
    """Activate a version by updating the active symlink and launcher.

    Args:
        tag: Version string to link.
        cfg: Runtime configuration.
        is_explicit_use: Whether invoked by 'use' command.

    Returns:
        Path to the activated JAR file.
    """
    target_jar = download_and_cache_version(tag, cfg)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would link {format_path_for_display(cfg.jar_symlink)} -> {format_path_for_display(target_jar)}[/yellow]"
        )
        return target_jar

    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    if cfg.jar_symlink.is_symlink() or cfg.jar_symlink.exists():
        cfg.jar_symlink.unlink()

    cfg.jar_symlink.symlink_to(target_jar)
    create_launcher(cfg.jar_symlink, cfg.bin_dir, cfg)

    console.print()
    console.print("[bold green]PlantUML successfully configured![/bold green]")
    console.print(f"  Cached JAR:   {format_path_for_display(target_jar)}")
    console.print(
        f"  Active Link:  {format_path_for_display(cfg.jar_symlink)} -> {format_path_for_display(target_jar)}"
    )
    console.print(f"  Launcher:     {format_path_for_display(cfg.wrapper_path)}")

    path_env = os.environ.get("PATH", "")
    bin_str = str(cfg.bin_dir)
    if bin_str not in path_env.split(os.pathsep):
        disp_bin = format_path_for_display(cfg.bin_dir)
        console.print()
        console.print("=" * 72)
        console.print(f"[bold yellow]NOTE:[/bold yellow] '{disp_bin}' is not in your current PATH.")
        console.print()
        console.print("To use 'plantuml' directly from your terminal, add it to your PATH:")
        console.print()
        console.print(f'  export PATH="{disp_bin}:$PATH"')
        console.print()
        console.print("To persist this change across shell sessions, add that line to your")
        console.print("shell configuration file (e.g. ~/.bashrc or ~/.zshrc).")
        console.print("=" * 72)
    console.print()
    return target_jar


def clean_cache(cfg: Config) -> int:
    """Remove inactive cached JAR files from cache directory.

    Args:
        cfg: Runtime configuration.

    Returns:
        Number of removed JAR files.
    """
    removed_count = 0
    active_target = get_active_target(cfg.jar_symlink)

    if not cfg.cache_dir.is_dir():
        return 0

    for item in cfg.cache_dir.iterdir():
        if (
            item.name.startswith("plantuml-")
            and item.name.endswith(".jar")
            and (
                not active_target
                or (item.name != active_target.name and item.resolve() != active_target.resolve())
            )
        ):
            cfg.log(f"Removing inactive cached JAR: {item}")
            if not cfg.dry_run:
                item.unlink()
                asc_file = item.with_suffix(".jar.asc")
                if asc_file.exists():
                    asc_file.unlink()
            removed_count += 1

    return removed_count


def uninstall_plantuml(
    cfg: Config,
    purge: bool = False,
) -> tuple[Path | None, Path | None, list[Path]]:
    """Uninstall PlantUML by removing launcher wrapper, active symlink, and optionally caches.

    Args:
        cfg: Runtime configuration.
        purge: Whether to remove cached JARs and downloads as well.

    Returns:
        A tuple of (removed_wrapper, removed_symlink, removed_cache_items).
    """
    removed_wrapper: Path | None = None
    removed_link: Path | None = None
    removed_cache: list[Path] = []

    if cfg.wrapper_path.is_file() or cfg.wrapper_path.is_symlink():
        removed_wrapper = cfg.wrapper_path
        if not cfg.dry_run:
            try:
                cfg.wrapper_path.unlink()
            except OSError:  # pragma: no cover
                pass

    if cfg.jar_symlink.is_symlink() or cfg.jar_symlink.exists():
        removed_link = cfg.jar_symlink
        if not cfg.dry_run:
            try:
                cfg.jar_symlink.unlink()
            except OSError:  # pragma: no cover
                pass

    if purge and cfg.cache_dir.is_dir():
        for item in cfg.cache_dir.iterdir():
            if not item.name.startswith("."):
                removed_cache.append(item)
                if not cfg.dry_run:
                    try:
                        if item.is_dir() and not item.is_symlink():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except OSError:  # pragma: no cover
                        pass

    return removed_wrapper, removed_link, removed_cache


def render_which(cfg: Config) -> None:
    """Print the location of the active JAR and wrapper script.

    Args:
        cfg: Runtime configuration.
    """
    active_target = get_active_target(cfg.jar_symlink)
    console.print("[bold]PlantUML Locations:[/bold]")
    if active_target and active_target.exists():
        console.print(f"  Active JAR:    {format_path_for_display(active_target)}")
    else:
        console.print("  Active JAR:    [red]none (not installed or unlinked)[/red]")

    if cfg.jar_symlink.exists():
        console.print(f"  Symlink:       {format_path_for_display(cfg.jar_symlink)}")
    else:
        console.print("  Symlink:       [red]none[/red]")

    if cfg.wrapper_path.exists():
        console.print(f"  Launcher:      {format_path_for_display(cfg.wrapper_path)}")
    else:
        console.print("  Launcher:      [red]none (wrapper missing)[/red]")

    path_env = os.environ.get("PATH", "").split(os.pathsep)
    if str(cfg.bin_dir) in path_env or str(cfg.bin_dir.resolve()) in path_env:
        console.print("  PATH Status:   [green]Launcher directory is in PATH[/green]")
    else:
        console.print(
            f"  PATH Status:   [yellow]Launcher directory is NOT in PATH ({format_path_for_display(cfg.bin_dir)})[/yellow]"
        )


def create_transient_launcher(target_jar: Path, cfg: Config) -> tuple[Path, Path]:
    """Create a temporary launcher script for exec against target_jar.

    Args:
        target_jar: Direct path to JAR file.
        cfg: Runtime configuration.

    Returns:
        Tuple of (temp_bin_dir, path_to_launcher).
    """
    tmp_bin = Path(tempfile.mkdtemp(prefix="puml_exec_"))
    wrapper = tmp_bin / "plantuml"
    content = f"""#!/usr/bin/env bash
set -euo pipefail
exec java -jar "{target_jar.resolve()}" "$@"
"""
    wrapper.write_text(content, encoding="utf-8")
    wrapper.chmod(0o755)
    return tmp_bin, wrapper


def run_exec_command(
    command_args: list[str],
    bin_dir_to_use: Path,
    temp_dir_to_cleanup: Path | None,
    cfg: Config,
) -> None:
    """Execute a shell command with PlantUML bin directory prepended.

    Args:
        command_args: Command and arguments to execute.
        bin_dir_to_use: Directory to prepend to PATH.
        temp_dir_to_cleanup: Temporary directory to clean up after execution.
        cfg: Runtime configuration.

    Raises:
        typer.Exit: Exits with the command's return code.
    """
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir_to_use.resolve()}{os.pathsep}{env.get('PATH', '')}"

    cfg.log(f"Executing command: {' '.join(command_args)}")
    try:
        res = subprocess.run(command_args, env=env, check=False)
        returncode = res.returncode
    except FileNotFoundError:
        err_console.print(f"[red]error:[/red] Executable not found: {command_args[0]}")
        returncode = 127
    finally:
        if temp_dir_to_cleanup and temp_dir_to_cleanup.is_dir():
            shutil.rmtree(temp_dir_to_cleanup, ignore_errors=True)

    raise typer.Exit(returncode)


# CLI Application
app = typer.Typer(
    name=Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-plantuml",
    help="Manages PlantUML standalone JAR versions, cache storage, and launcher binary.",
    no_args_is_help=True,
    add_completion=False,
)


def cli_version_callback(value: bool) -> None:
    """Print version string and exit."""
    if value:
        root = find_project_root()
        ver = get_project_version(root)
        console.print(f"install_plantuml.py (cs1302-book {ver})")
        raise typer.Exit(0)


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[
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
) -> None:
    """Configure runtime options in Typer context."""
    cfg = create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    ctx.obj = cfg


@app.command("install", help="Install specified (or latest) release into cache and link.")
def cmd_install(
    tag: Annotated[
        str,
        typer.Argument(
            help="Release version tag to install, or 'latest'",
        ),
    ] = "latest",
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Install specified (or latest) release into cache and link."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    clean_tag = clean_version_tag(tag)
    if clean_tag.lower() == "latest":
        latest = get_latest_github_version()
        if latest:
            clean_tag = latest

    target_jar = cfg.cache_dir / f"plantuml-{clean_tag}.jar"

    if not cfg.yes and not cfg.dry_run:
        prompt = f"Install and activate PlantUML v{clean_tag}?"
        if not typer.confirm(prompt, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    if target_jar.exists() and not cfg.force:
        console.print(f"Using existing cached JAR: {format_path_for_display(target_jar)}")

    apply_version_link(tag, cfg, is_explicit_use=False)


@app.command("update", help="Check GitHub and update to the latest release.")
def cmd_update(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Check GitHub and update to the latest release."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    current_ver = get_installed_version(cfg.jar_symlink)
    latest_ver = get_latest_github_version()

    if not latest_ver:
        err_console.print("[red]error:[/red] Unable to retrieve latest release from GitHub.")
        raise typer.Exit(1)

    if current_ver and is_version_ge(current_ver, latest_ver) and not cfg.force:
        console.print(f"PlantUML is already up to date ({current_ver}).")
        return

    if not cfg.yes and not cfg.dry_run:
        prompt = (
            f"Update PlantUML from {current_ver or 'none'} to {latest_ver}?"
            if current_ver
            else f"Install latest PlantUML release (v{latest_ver})?"
        )
        if not typer.confirm(prompt, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    apply_version_link("latest", cfg, is_explicit_use=False)


@app.command("use", help="Switch active version to TAG (downloads to cache if missing).")
def cmd_use(
    tag: Annotated[str, typer.Argument(help="Version tag to activate")],
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Switch active version to TAG."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    apply_version_link(tag, cfg, is_explicit_use=True)


@app.command("versions", help="List all downloaded cached versions and mark active link.")
@app.command("list", hidden=True)
@app.command("ls", hidden=True)
def cmd_versions(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """List all downloaded cached versions and mark active link."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    active_target = get_active_target(cfg.jar_symlink)
    installed_versions: list[tuple[str, bool]] = []

    if cfg.cache_dir.is_dir():
        for item in sorted(cfg.cache_dir.iterdir()):
            if item.name.startswith("plantuml-") and item.name.endswith(".jar"):
                clean_tag = clean_version_tag(item.name[len("plantuml-") : -len(".jar")])
                is_active = active_target and (
                    active_target.name == item.name or active_target.resolve() == item.resolve()
                )
                installed_versions.append((clean_tag, bool(is_active)))

    if not installed_versions:
        console.print("No PlantUML versions currently installed in cache.")
        return

    table = Table(title="Installed PlantUML Versions", box=None)
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="green")

    for ver, active in installed_versions:
        status_str = "* active" if active else ""
        table.add_row(ver, status_str)

    console.print(table)


@app.command("status", help="Display current version, latest release, and symlink paths.")
def cmd_status(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display current version, latest release, and symlink paths."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    installed_ver = get_installed_version(cfg.jar_symlink)
    with err_console.status(
        "[bold cyan]Checking latest GitHub release...[/bold cyan]", spinner="dots"
    ):
        latest_ver = get_latest_github_version()

    root = find_project_root()
    min_ver = get_min_jar_version(root)

    console.print("[bold]PlantUML Installation Status:[/bold]")
    console.print(f"  Active version:       {installed_ver or 'none (not installed)'}")
    console.print(f"  Latest GitHub tag:    {latest_ver or 'unknown'}")
    if min_ver:
        console.print(f"  Project min version:  {min_ver}")

    console.print()
    if not installed_ver:
        console.print(
            "[yellow]Status: PlantUML is not installed. Run 'install_plantuml.py install' to install.[/yellow]"
        )
    elif latest_ver and is_version_ge(installed_ver, latest_ver):
        console.print("[green]Status: PlantUML is up to date.[/green]")
    elif latest_ver and not is_version_ge(installed_ver, latest_ver):
        console.print(
            f"[yellow]Status: Update available ({installed_ver} -> {latest_ver}). Run 'install_plantuml.py update' to upgrade.[/yellow]"
        )
    elif min_ver and not is_version_ge(installed_ver, min_ver):
        console.print(
            f"[red]Status: Installed version ({installed_ver}) does not satisfy project min requirement (>={min_ver}).[/red]"
        )


@app.command("clean", help="Remove cached JARs that are not currently active.")
@app.command("prune", hidden=True)
def cmd_clean(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Remove cached JARs that are not currently active."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    active_target = get_active_target(cfg.jar_symlink)
    unused_jars: list[Path] = []
    if cfg.cache_dir.is_dir():
        for item in cfg.cache_dir.iterdir():
            if (
                item.name.startswith("plantuml-")
                and item.name.endswith(".jar")
                and (
                    not active_target
                    or (
                        item.name != active_target.name
                        and item.resolve() != active_target.resolve()
                    )
                )
            ):
                unused_jars.append(item)

    if not unused_jars:
        console.print("No unused cached JARs found.")
        return

    if (
        not cfg.yes
        and not cfg.dry_run
        and not typer.confirm(f"Remove {len(unused_jars)} unused cached JAR(s)?", default=True)
    ):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Scanning unused PlantUML cache in {format_path_for_display(cfg.cache_dir)}...[/yellow]"
        )
    else:
        console.print(
            f"Cleaning unused PlantUML cache in {format_path_for_display(cfg.cache_dir)}..."
        )

    removed = clean_cache(cfg)

    if cfg.dry_run:
        console.print(f"[yellow]\\[dry-run] Would remove {removed} unused JAR(s).[/yellow]")
    else:
        console.print(f"Done. Removed {removed} unused JAR(s).")


@app.command("uninstall", help="Uninstall PlantUML launcher and active installation.")
def cmd_uninstall(
    purge: OptPurge = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Uninstall PlantUML by removing launcher wrapper and active JAR symlink."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    prompt_msg = (
        "Uninstall PlantUML and remove all cached JARs?"
        if purge
        else "Uninstall PlantUML (remove launcher and active symlink)?"
    )
    if not cfg.yes and not cfg.dry_run and not typer.confirm(prompt_msg, default=True):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    if cfg.dry_run:
        console.print("[yellow]\\[dry-run] Simulating PlantUML uninstallation...[/yellow]")
    else:
        console.print("Uninstalling PlantUML...")

    removed_wrapper, removed_link, removed_cache = uninstall_plantuml(cfg, purge=purge)

    if cfg.dry_run:
        if removed_wrapper:
            console.print(
                f"[yellow]\\[dry-run] Would remove launcher: {format_path_for_display(removed_wrapper)}[/yellow]"
            )
        if removed_link:
            console.print(
                f"[yellow]\\[dry-run] Would remove active link: {format_path_for_display(removed_link)}[/yellow]"
            )
        if purge:
            console.print(
                f"[yellow]\\[dry-run] Would remove {len(removed_cache)} cached item(s)[/yellow]"
            )
    else:
        if removed_wrapper:
            console.print(f"Removed launcher: {format_path_for_display(removed_wrapper)}")
        if removed_link:
            console.print(f"Removed active link: {format_path_for_display(removed_link)}")
        if purge:
            console.print(f"Removed {len(removed_cache)} cached item(s).")
        console.print("[bold green]PlantUML successfully uninstalled.[/bold green]")


@app.command("which", help="Display active JAR path and launcher binary location.")
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display active JAR path and launcher binary location."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    render_which(cfg)


@app.command(
    "exec",
    help="Run a command with PlantUML bin directory prepended to PATH.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@app.command(
    "run",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_exec(
    use: Annotated[
        str | None,
        typer.Option(
            "--use",
            "-u",
            help="Run command against a specific version (cached or downloaded on the fly)",
        ),
    ] = None,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Run a command with PlantUML bin directory prepended to PATH."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    extra_args = list(ctx.args) if ctx and ctx.args else []
    if not extra_args:
        err_console.print("[red]error:[/red] No command specified to execute.")
        raise typer.Exit(1)

    if use:
        clean_tag = clean_version_tag(use)
        target_jar = cfg.cache_dir / f"plantuml-{clean_tag}.jar"
        if not target_jar.exists():
            download_and_cache_version(use, cfg)

        tmp_dir, _ = create_transient_launcher(target_jar, cfg)
        run_exec_command(extra_args, tmp_dir, tmp_dir, cfg)
    else:
        if not cfg.wrapper_path.exists():
            apply_version_link("latest", cfg, is_explicit_use=False)
        run_exec_command(extra_args, cfg.bin_dir, None, cfg)


@app.command(
    "rehash",
    help="Clear and regenerate PlantUML wrapper in scripts/installer/shims/bin (or custom bin-dir).",
)
def cmd_rehash(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Clear and rebuild PlantUML executable wrapper shim."""
    root = find_project_root()
    target_bin = bin_dir or resolve_shims_bin_dir(root)
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
    )
    active_target = get_active_target(cfg.jar_symlink)
    if not active_target or not active_target.exists():
        console.print(
            "[yellow]PlantUML is not currently installed or linked. Run 'install-plantuml install' first.[/yellow]"
        )
        return

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would clear and recreate PlantUML wrapper in {format_path_for_display(cfg.bin_dir)}[/yellow]"
        )
        return

    if cfg.wrapper_path.exists():
        try:
            cfg.wrapper_path.unlink()
        except OSError:  # pragma: no cover
            pass

    wrapper = create_launcher(active_target, cfg.bin_dir, cfg)
    console.print(
        f"[bold green]Rehashed PlantUML wrapper at {format_path_for_display(wrapper)}.[/bold green]"
    )


@app.command("help", help="Display help information for PlantUML installer or a specific command.")
def cmd_help(
    command_name: Annotated[
        str | None,
        typer.Argument(
            metavar="COMMAND",
            help="The command to display help information for.",
        ),
    ] = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display help information for PlantUML installer or a specific command."""
    cli_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-plantuml"
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
        console.print(f"install_plantuml.py (cs1302-book {ver})")


@self_app.command("path", help="Display the path of this script.")
@self_app.command("which", hidden=True)
def cmd_self_path() -> None:
    """Display the path of this script."""
    console.print(format_path_for_display(Path(__file__).resolve()))


def main() -> None:
    """Main CLI entry point for the script."""
    try:
        app()
    except Exception as e:  # noqa: BLE001
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1) from None


if __name__ == "__main__":  # pragma: no cover
    main()
