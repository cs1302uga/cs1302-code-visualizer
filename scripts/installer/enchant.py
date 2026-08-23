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
"""Enchant standalone version and installation manager.

Downloads source releases for Enchant (libenchant-2) from GitHub Releases,
builds and installs them into a versioned cache directory, and manages active
executables and man pages via atomic symlinks and shims.
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
    resolve_default_man_dir,
)
from scripts.installer.common import (
    download_file as common_download_file,
)
from scripts.installer.graphviz import OptManDir

console = Console()
err_console = Console(stderr=True)

GITHUB_RELEASES_API = "https://api.github.com/repos/rrthomas/enchant/releases"
GITHUB_SOURCE_URL_TEMPLATE = (
    "https://github.com/rrthomas/enchant/releases/download/v{version}/enchant-{version}.tar.gz"
)
DEFAULT_FALLBACK_VERSION = "2.8.2"

ENCHANT_KNOWN_BINARIES: frozenset[str] = frozenset({
    "enchant",
    "enchant-2",
    "enchant-lsmod",
    "enchant-lsmod-2",
})


def get_min_enchant_version(root_dir: Path) -> str | None:
    """Read minimum Enchant version from pyproject.toml.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Configured minimum version string if present, else None.
    """
    return get_min_system_dependency_version(root_dir, "enchant")


@dataclass
class Config:
    """Runtime configuration and filesystem locations.

    Attributes:
        install_dir: Directory containing the active symlink.
        cache_dir: Directory storing versioned installations and downloads.
        bin_dir: Directory containing launcher shims.
        man_dir: Directory containing man pages.
        verbose: Whether verbose logging is enabled.
        dry_run: Whether dry-run mode is active.
        force: Whether to force re-download / link overwrite.
        yes: Whether to automatically accept all interactive prompts.
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
        """Path to the active installation symlink."""
        return self.install_dir / "current"

    @property
    def primary_executable(self) -> Path:
        """Path to the primary 'enchant' launcher executable."""
        return self.bin_dir / "enchant"

    def log(self, message: str) -> None:
        """Print verbose log if enabled.

        Args:
            message: Message to log to standard error.
        """
        if self.verbose:
            err_console.print(f"[dim][install_enchant.py][/dim] {message}")


def resolve_default_paths(root_dir: Path | None = None) -> tuple[Path, Path, Path, Path]:
    """Resolve default directories based on the project root directory.

    Args:
        root_dir: Optional root directory of the project.

    Returns:
        A tuple of (default_install_dir, default_cache_dir, default_bin_dir, default_man_dir).
    """
    root = root_dir or find_project_root()
    default_install_dir = root / "scripts" / "cache" / "enchant"
    default_cache_dir = root / "scripts" / "cache" / "enchant"
    default_bin_dir = resolve_default_bin_dir(root)
    default_man_dir = resolve_default_man_dir(root)
    return default_install_dir, default_cache_dir, default_bin_dir, default_man_dir


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
    """Create a Config object with project defaults and CLI overrides.

    Args:
        dir_path: Custom install directory override.
        cache_dir: Custom cache directory override.
        bin_dir: Custom launcher binary directory override.
        man_dir: Custom man directory override.
        verbose: Verbose output flag.
        dry_run: Dry-run execution flag.
        force: Force re-download / overwrite flag.
        yes: Automatic yes confirmation flag.

    Returns:
        Configured Config instance.
    """
    def_install, def_cache, def_bin, def_man = resolve_default_paths()
    env_verbose = os.environ.get("VERBOSE", "0") in ("1", "true", "True")
    env_install = os.environ.get("ENCHANT_INSTALL_DIR") or os.environ.get("CS1302_INSTALL_DIR")
    env_cache = os.environ.get("ENCHANT_CACHE_DIR") or os.environ.get("CS1302_CACHE_DIR")
    env_bin = os.environ.get("ENCHANT_BIN_DIR") or os.environ.get("CS1302_BIN_DIR")
    env_man = os.environ.get("ENCHANT_MAN_DIR") or os.environ.get("CS1302_MAN_DIR")

    return Config(
        install_dir=dir_path or (Path(env_install) if env_install else def_install),
        cache_dir=cache_dir or (Path(env_cache) if env_cache else def_cache),
        bin_dir=bin_dir or (Path(env_bin) if env_bin else def_bin),
        man_dir=man_dir or (Path(env_man) if env_man else def_man),
        verbose=verbose or env_verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )


def get_installed_version(target_path: Path) -> str | None:
    """Detect the version of an installed Enchant binary.

    Args:
        target_path: Path to the active symlink or installation directory.

    Returns:
        Clean version string if detected, else None.
    """
    if not target_path.exists():
        return None

    # Locate executable
    candidates = [
        target_path / "bin" / "enchant-2",
        target_path / "bin" / "enchant",
        target_path / "enchant-2",
        target_path / "enchant",
    ]
    exec_bin = None
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

    env = os.environ.copy()
    lib_dir = target_path / "lib"
    if lib_dir.is_dir():
        if platform.system() == "Darwin":
            env["DYLD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('DYLD_LIBRARY_PATH', '')}"
        else:
            env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"

    try:
        res = subprocess.run(
            [str(exec_bin), "-v"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        out = res.stderr or res.stdout
        if out:
            match = re.search(
                r"(?:Enchant|enchant-lsmod(?:-\d+)?)\s+(\d+\.\d+(?:\.\d+)?)",
                out,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(r"(\d+\.\d+(?:\.\d+)?)", out)
            if match:
                return match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass

    # Fallback to directory name pattern if executable output fails
    resolved_dir = target_path.resolve() if target_path.is_symlink() else target_path
    match_dir = re.search(r"(\d+\.\d+(?:\.\d+)?)", resolved_dir.name)
    if match_dir:
        return match_dir.group(1)

    return None


def get_latest_github_version() -> str:
    """Fetch the latest release version of Enchant from GitHub.

    Returns:
        Version string of the latest release.
    """
    try:
        resp = requests.get(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            releases = resp.json()
            for rel in releases:
                if not rel.get("prerelease", False) and not rel.get("draft", False):
                    tag = rel.get("tag_name", "")
                    clean_ver = clean_version_tag(tag)
                    if clean_ver and clean_ver[0].isdigit():
                        return clean_ver
    except (requests.RequestException, ValueError, KeyError):
        pass
    return DEFAULT_FALLBACK_VERSION


def get_github_release_versions() -> list[str]:
    """Fetch available release version tags of Enchant from GitHub.

    Returns:
        List of release version strings.
    """
    versions: list[str] = []
    try:
        resp = requests.get(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            releases = resp.json()
            for rel in releases:
                if not rel.get("prerelease", False) and not rel.get("draft", False):
                    tag = rel.get("tag_name", "")
                    clean_ver = clean_version_tag(tag)
                    if clean_ver and clean_ver not in versions:
                        versions.append(clean_ver)
    except (requests.RequestException, ValueError, KeyError):
        pass

    if not versions:
        versions = [DEFAULT_FALLBACK_VERSION, "2.8.1", "2.8.0"]
    return versions


def resolve_target_tag(requested_version: str | None, cfg: Config) -> tuple[str, str]:
    """Resolve user-requested version string into clean version and download URL.

    Args:
        requested_version: User provided version (e.g. 'latest', '2.8.2', 'v2.8.2').
        cfg: Runtime configuration.

    Returns:
        Tuple of (clean_version_tag, source_download_url).
    """
    if not requested_version or requested_version.lower() == "latest":
        clean_tag = get_latest_github_version()
    else:
        clean_tag = clean_version_tag(requested_version)

    url = GITHUB_SOURCE_URL_TEMPLATE.format(version=clean_tag)
    cfg.log(f"Resolved version '{requested_version}' -> tag '{clean_tag}' (URL: {url})")
    return clean_tag, url


def download_and_build_enchant(version_str: str, cfg: Config) -> Path:
    """Download, configure, build, and install Enchant into the cache directory.

    Args:
        version_str: Clean version string to install.
        cfg: Runtime configuration.

    Returns:
        Path to the installed version directory.

    Raises:
        typer.Exit: If download or compilation fails.
    """
    target_version_dir = cfg.cache_dir / version_str
    if target_version_dir.is_dir() and not cfg.force:
        installed_ver = get_installed_version(target_version_dir)
        if installed_ver:
            cfg.log(f"Version {version_str} is already built at {target_version_dir}")
            return target_version_dir

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would download and build Enchant {version_str} to {format_path_for_display(target_version_dir)}[/yellow]"
        )
        return target_version_dir

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    _, download_url = resolve_target_tag(version_str, cfg)
    tarball_path = cfg.cache_dir / f"enchant-{version_str}.tar.gz"

    if not tarball_path.is_file() or cfg.force:
        cfg.log(f"Downloading Enchant source from {download_url}...")
        _ = common_download_file(download_url, tarball_path, f"Enchant v{version_str} source")

    tmp_work_dir = Path(tempfile.mkdtemp(prefix="enchant_build_"))
    extract_src_dir = tmp_work_dir / f"enchant-{version_str}"

    try:
        with (
            err_console.status(
                f"[bold cyan]Extracting Enchant v{version_str}...[/bold cyan]", spinner="dots"
            ),
            tarfile.open(tarball_path, "r:gz") as tar,
        ):
            tar.extractall(tmp_work_dir, numeric_owner=True, filter="tar")

        if not extract_src_dir.is_dir():
            subdirs = [p for p in tmp_work_dir.iterdir() if p.is_dir()]
            if subdirs:
                extract_src_dir = subdirs[0]

        configure_script = extract_src_dir / "configure"
        if not configure_script.is_file():
            err_console.print(
                f"[red]error:[/red] 'configure' script not found in {extract_src_dir}."
            )
            raise typer.Exit(1)

        prefix_path = target_version_dir.resolve()
        target_version_dir.mkdir(parents=True, exist_ok=True)

        with err_console.status(
            f"[bold cyan]Configuring Enchant v{version_str}...[/bold cyan]", spinner="dots"
        ):
            cfg.log(f"Running ./configure --prefix={prefix_path} in {extract_src_dir}")
            conf_res = subprocess.run(
                [
                    "./configure",
                    f"--prefix={prefix_path}",
                    "--disable-static",
                    "--enable-shared",
                ],
                cwd=extract_src_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if conf_res.returncode != 0:
                err_console.print(
                    f"[red]error:[/red] ./configure failed:\n{conf_res.stderr or conf_res.stdout}"
                )
                raise typer.Exit(1)

        cpu_count = os.cpu_count() or 2
        with err_console.status(
            f"[bold cyan]Compiling Enchant v{version_str} (jobs: {cpu_count})...[/bold cyan]",
            spinner="dots",
        ):
            cfg.log(f"Running make -j{cpu_count} in {extract_src_dir}")
            make_res = subprocess.run(
                ["make", f"-j{cpu_count}", "nodist_doc_DATA="],
                cwd=extract_src_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if make_res.returncode != 0:
                err_console.print(
                    f"[red]error:[/red] make failed:\n{make_res.stderr or make_res.stdout}"
                )
                raise typer.Exit(1)

        with err_console.status(
            f"[bold cyan]Installing Enchant v{version_str}...[/bold cyan]", spinner="dots"
        ):
            cfg.log(f"Running make install in {extract_src_dir}")
            inst_res = subprocess.run(
                ["make", "install", "nodist_doc_DATA="],
                cwd=extract_src_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if inst_res.returncode != 0:
                err_console.print(
                    f"[red]error:[/red] make install failed:\n{inst_res.stderr or inst_res.stdout}"
                )
                raise typer.Exit(1)

        cfg.log(f"Enchant successfully built and installed to {target_version_dir}")
        return target_version_dir

    finally:
        shutil.rmtree(tmp_work_dir, ignore_errors=True)


def create_launcher_shims(version_dir: Path, cfg: Config) -> list[Path]:
    """Create executable launcher shims for Enchant in the binary directory.

    Args:
        version_dir: Path to the active Enchant version installation.
        cfg: Runtime configuration.

    Returns:
        List of created shim file paths.
    """
    created: list[Path] = []
    cfg.bin_dir.mkdir(parents=True, exist_ok=True)
    cfg.log(f"Creating launcher shims in {cfg.bin_dir} -> {version_dir}")

    # Map aliases to actual binaries in version_dir/bin
    bin_mappings = {
        "enchant": "enchant-2" if (version_dir / "bin" / "enchant-2").exists() else "enchant",
        "enchant-2": "enchant-2" if (version_dir / "bin" / "enchant-2").exists() else "enchant",
        "enchant-lsmod": "enchant-lsmod-2"
        if (version_dir / "bin" / "enchant-lsmod-2").exists()
        else "enchant-lsmod",
        "enchant-lsmod-2": "enchant-lsmod-2"
        if (version_dir / "bin" / "enchant-lsmod-2").exists()
        else "enchant-lsmod",
    }

    for shim_name, target_rel in bin_mappings.items():
        shim_path = cfg.bin_dir / shim_name
        if cfg.dry_run:
            console.print(
                f"[yellow]\\[dry-run] Would create launcher shim: {format_path_for_display(shim_path)}[/yellow]"
            )
            created.append(shim_path)
            continue

        shim_content = f"""#!/usr/bin/env bash
#
# Enchant launcher shim generated by install_enchant.py
set -euo pipefail

ENCHANT_HOME="{version_dir.resolve()}"
export ENCHANT_HOME

if [[ "$(uname -s)" == "Darwin" ]]; then
    export DYLD_LIBRARY_PATH="${{ENCHANT_HOME}}/lib:${{DYLD_LIBRARY_PATH:-}}"
else
    export LD_LIBRARY_PATH="${{ENCHANT_HOME}}/lib:${{LD_LIBRARY_PATH:-}}"
fi

TARGET_BIN="${{ENCHANT_HOME}}/bin/{target_rel}"

if [[ ! -f "${{TARGET_BIN}}" ]]; then
    TARGET_BIN="${{ENCHANT_HOME}}/bin/{shim_name}"
fi

if [[ ! -f "${{TARGET_BIN}}" ]]; then
    printf "error: Enchant binary not found at %s. Please run 'install-enchant install' to reinstall.\\n" "${{TARGET_BIN}}" >&2
    exit 1
fi

exec "${{TARGET_BIN}}" "$@"
"""
        _ = shim_path.write_text(shim_content, encoding="utf-8")
        shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        created.append(shim_path)

    return created


def create_man_links(version_dir: Path, cfg: Config) -> list[Path]:
    """Create symlinks or copy man pages into the configured man directory.

    Args:
        version_dir: Path to the active Enchant installation directory.
        cfg: Runtime configuration.

    Returns:
        List of created man page links.
    """
    created: list[Path] = []
    src_man = version_dir / "share" / "man"
    if not src_man.is_dir():
        return created

    for man_section in src_man.glob("man*"):
        if man_section.is_dir():
            target_section = cfg.man_dir / man_section.name
            target_section.mkdir(parents=True, exist_ok=True)
            for page in man_section.glob("*.*"):
                if page.is_file():
                    target_page = target_section / page.name
                    if cfg.dry_run:
                        console.print(
                            f"[yellow]\\[dry-run] Would link man page: {format_path_for_display(target_page)}[/yellow]"
                        )
                        created.append(target_page)
                    else:
                        if target_page.is_symlink() or target_page.exists():
                            target_page.unlink()
                        target_page.symlink_to(page.resolve())
                        created.append(target_page)
    return created


def apply_version_link(
    version_tag: str,
    cfg: Config,
    is_explicit_use: bool = False,
) -> None:
    """Download, build, and activate the specified Enchant version.

    Args:
        version_tag: Version string or 'latest'.
        cfg: Runtime configuration.
        is_explicit_use: Whether this installation was triggered explicitly.
    """
    _ = is_explicit_use
    clean_tag, _ = resolve_target_tag(version_tag, cfg)

    current_installed = get_installed_version(cfg.current_link)
    cfg.log(f"Current installed version: {current_installed or 'none'}, target: {clean_tag}")

    if not cfg.yes and not cfg.dry_run:
        prompt_msg = (
            f"Update Enchant from {current_installed} to {clean_tag}?"
            if current_installed and current_installed != clean_tag
            else f"Install and activate Enchant {clean_tag}?"
        )
        if not typer.confirm(prompt_msg, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    version_dir = download_and_build_enchant(clean_tag, cfg)

    if cfg.dry_run:
        console.print("\n[bold cyan][dry-run] Enchant Execution Plan:[/bold cyan]")
        console.print(f"  Target Version: [green]{clean_tag}[/green]")
        console.print(f"  Installed Path: {format_path_for_display(version_dir)}")
        console.print(
            f"  Active Link:    {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}"
        )
        console.print(f"  Shims Dir:      {format_path_for_display(cfg.bin_dir)}")
        console.print(f"  Man Dir:        {format_path_for_display(cfg.man_dir)}\n")
        return

    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    if cfg.current_link.is_symlink():
        cfg.current_link.unlink()
    elif cfg.current_link.is_dir():
        shutil.rmtree(cfg.current_link, ignore_errors=True)
    elif cfg.current_link.exists():
        cfg.current_link.unlink()

    cfg.current_link.symlink_to(version_dir.resolve())
    created_shims = create_launcher_shims(version_dir, cfg)
    created_man = create_man_links(version_dir, cfg)

    console.print("\n[bold green]Enchant successfully configured![/bold green]")
    console.print(f"  Installed Path: {format_path_for_display(version_dir)}")
    console.print(
        f"  Active Link:    {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}"
    )
    console.print(
        f"  Created Shims:  {len(created_shims)} binaries in {format_path_for_display(cfg.bin_dir)}"
    )
    if created_man:
        console.print(
            f"  Created Man:    {len(created_man)} man pages in {format_path_for_display(cfg.man_dir)}"
        )

    current_path = os.environ.get("PATH", "").split(os.pathsep)
    if str(cfg.bin_dir.resolve()) not in [str(Path(p).resolve()) for p in current_path if p]:
        console.print("=" * 72, style="yellow")
        console.print(
            f"NOTE: '{format_path_for_display(cfg.bin_dir)}' is not in your current PATH.\n",
            style="bold yellow",
        )
        console.print("To use 'enchant' directly from your terminal, add it to your PATH:\n")
        console.print(
            f'  export PATH="{format_path_for_display(cfg.bin_dir)}:$PATH"\n', style="bold green"
        )
        console.print("=" * 72 + "\n", style="yellow")


def render_versions_table(cfg: Config) -> None:
    """Render a table of all cached Enchant versions.

    Args:
        cfg: Runtime configuration.
    """
    table = Table(title="Cached Enchant Versions", box=None)
    table.add_column("", justify="center", style="bold green", width=3)
    table.add_column("Version", style="bold cyan", width=16)
    table.add_column("Location", style="dim")

    count = 0
    active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None

    if cfg.cache_dir.is_dir():
        for entry in sorted(cfg.cache_dir.iterdir()):
            if entry.is_dir() and entry.name != "current":
                installed_ver = get_installed_version(entry) or entry.name
                is_active = active_target and (active_target == entry.resolve())
                marker = "*" if is_active else ""
                table.add_row(marker, installed_ver, format_path_for_display(entry))
                count += 1

    if count > 0:
        console.print(table)
    else:
        console.print(
            f"  (no cached Enchant installations found in {format_path_for_display(cfg.cache_dir)})"
        )

    console.print(
        f"\nActive link: {format_path_for_display(cfg.current_link)} -> {format_path_for_display(active_target)}"
    )


def render_status(cfg: Config) -> None:
    """Display active Enchant version status, latest upstream release, and paths.

    Args:
        cfg: Runtime configuration.
    """
    with err_console.status(
        "[bold cyan]Checking active Enchant status...[/bold cyan]", spinner="dots"
    ):
        active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None
        active_ver = get_installed_version(cfg.current_link) if cfg.current_link.exists() else None
        latest_ver = get_latest_github_version()
        min_ver = get_min_enchant_version(find_project_root())

    console.print("[bold]Enchant Installation Status:[/bold]")
    console.print(f"  Active version:       [cyan]{active_ver or 'none (not installed)'}[/cyan]")
    console.print(f"  Latest GitHub tag:    [green]{latest_ver}[/green]")
    if min_ver:
        console.print(f"  Project min version:  {min_ver}")
    console.print(f"  Installed location:   {format_path_for_display(active_target)}")
    console.print(f"  Shims directory:      {format_path_for_display(cfg.bin_dir)}")
    console.print(f"  Man directory:        {format_path_for_display(cfg.man_dir)}")

    if not active_ver:
        console.print(
            "\n[bold yellow]Status: Enchant is not installed. Run 'install-enchant install' to install.[/bold yellow]"
        )
    elif min_ver and not is_version_ge(active_ver, min_ver):
        console.print(
            f"\n[bold red]Status: Active version ({active_ver}) does not satisfy project minimum requirement ({min_ver}). "
            + f"Run 'install-enchant install {min_ver}' to upgrade.[/bold red]"
        )
    else:
        console.print("\n[bold green]Status: Enchant is up to date.[/bold green]")


def clean_cache(cfg: Config) -> int:
    """Remove cached Enchant versions that are not currently active.

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


def uninstall_enchant(
    cfg: Config,
    purge: bool = False,
) -> tuple[list[Path], Path | None, list[Path], list[Path]]:
    """Uninstall Enchant by removing launcher shims, active link, and optionally cache.

    Args:
        cfg: Runtime configuration.
        purge: Whether to remove all cached downloads and installations.

    Returns:
        Tuple of (removed_shims, removed_link, removed_cache_entries, removed_man_pages).
    """
    removed_shims: list[Path] = []
    removed_man: list[Path] = []
    removed_cache: list[Path] = []
    removed_link: Path | None = None

    for bin_name in ENCHANT_KNOWN_BINARIES:
        shim_path = cfg.bin_dir / bin_name
        if shim_path.is_file() or shim_path.is_symlink():
            if not cfg.dry_run:
                shim_path.unlink(missing_ok=True)
            removed_shims.append(shim_path)

    if cfg.man_dir.is_dir():
        for section in cfg.man_dir.glob("man*"):
            if section.is_dir():
                for man_page in section.glob("enchant*"):
                    if not cfg.dry_run:
                        man_page.unlink(missing_ok=True)
                    removed_man.append(man_page)

    if cfg.current_link.is_symlink() or cfg.current_link.exists():
        removed_link = cfg.current_link
        if not cfg.dry_run:
            if cfg.current_link.is_dir() and not cfg.current_link.is_symlink():
                shutil.rmtree(cfg.current_link, ignore_errors=True)
            else:
                cfg.current_link.unlink(missing_ok=True)

    if purge and cfg.cache_dir.is_dir():
        for entry in cfg.cache_dir.iterdir():
            if not cfg.dry_run:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
            removed_cache.append(entry)

    return removed_shims, removed_link, removed_cache, removed_man


def render_which(cfg: Config) -> None:
    """Display active Enchant binary location, symlink, and PATH status.

    Args:
        cfg: Runtime configuration.
    """
    active_target = cfg.current_link.resolve() if cfg.current_link.is_symlink() else None
    primary_bin = cfg.bin_dir / "enchant"
    in_path = str(cfg.bin_dir.resolve()) in [
        str(Path(p).resolve()) for p in os.environ.get("PATH", "").split(os.pathsep) if p
    ]

    console.print("[bold]Enchant Locations:[/bold]")
    console.print(f"  Active Installation: {format_path_for_display(active_target)}")
    console.print(f"  Active Link:         {format_path_for_display(cfg.current_link)}")
    console.print(f"  Primary Executable:  {format_path_for_display(primary_bin)}")
    if in_path:
        console.print("  PATH Status:         [green]Launcher directory is in PATH[/green]")
    else:
        console.print(
            f"  PATH Status:         [yellow]Launcher directory is NOT in PATH ({format_path_for_display(cfg.bin_dir)})[/yellow]"
        )


# Typer Application
app = typer.Typer(
    name="install-enchant",
    help="Manages Enchant spelling library versions, local builds, and launcher shims.",
    no_args_is_help=True,
    add_completion=False,
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
    """Extract or build Config from Typer Context with overrides.

    Args:
        ctx: Typer Context.
        verbose: Verbose flag override.
        dry_run: Dry-run flag override.
        force: Force flag override.
        yes: Automatic yes flag override.
        dir_path: Install directory override.
        cache_dir: Cache directory override.
        bin_dir: Binary directory override.
        man_dir: Man directory override.

    Returns:
        Config instance.
    """
    if ctx and isinstance(ctx.obj, Config):
        cfg = ctx.obj
    else:
        cfg = create_default_config()

    if verbose:
        cfg.verbose = True
    if dry_run:
        cfg.dry_run = True
    if force:
        cfg.force = True
    if yes:
        cfg.yes = True
    if dir_path is not None:
        cfg.install_dir = dir_path
    if cache_dir is not None:
        cfg.cache_dir = cache_dir
    if bin_dir is not None:
        cfg.bin_dir = bin_dir
    if man_dir is not None:
        cfg.man_dir = man_dir
    return cfg


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
        console.print(f"install_enchant.py (cs1302-code-visualizer {ver})")
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


@app.command("install", help="Download and compile specified (or latest) Enchant version.")
def cmd_install(
    version_tag: Annotated[
        str | None,
        typer.Argument(
            help="Specific Enchant version to install (e.g. 2.8.2, default: latest)",
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
    """Download and compile specified (or latest) Enchant version."""
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
    target = version_tag or "latest"
    apply_version_link(target, cfg, is_explicit_use=bool(version_tag))


@app.command("update", help="Check upstream for the latest Enchant release and upgrade.")
def cmd_update(
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
    """Check upstream for the latest Enchant release and upgrade."""
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
    latest_ver = get_latest_github_version()
    cfg.force = True
    apply_version_link(latest_ver, cfg, is_explicit_use=True)


@app.command("use", help="Switch active installation to VERSION (builds on demand).")
@app.command("set", hidden=True)
def cmd_use(
    version_tag: Annotated[
        str,
        typer.Argument(
            help="Release version to activate (e.g. 2.8.2)",
        ),
    ],
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
    """Switch active installation to VERSION (builds on demand)."""
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
    apply_version_link(version_tag, cfg, is_explicit_use=True)


@app.command("versions", help="List all cached Enchant versions and mark active link.")
@app.command("list", hidden=True)
@app.command("ls", hidden=True)
def cmd_versions(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """List all cached Enchant versions and mark active link."""
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


@app.command("status", help="Display current active Enchant version and paths.")
@app.command("check", hidden=True)
@app.command("info", hidden=True)
def cmd_status(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Display current active Enchant version and paths."""
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


@app.command("clean", help="Remove cached Enchant installations that are not active.")
@app.command("prune", hidden=True)
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
    """Remove cached Enchant installations that are not active."""
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
    removed = clean_cache(cfg)
    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would remove {removed} unused Enchant version(s).[/yellow]"
        )
    else:
        console.print(f"Done. Removed {removed} unused Enchant version(s).")


@app.command("uninstall", help="Uninstall Enchant shims and active installation.")
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
    """Uninstall Enchant by removing launcher shims, man pages, and active link."""
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
        "Uninstall Enchant and remove all cached builds?"
        if purge
        else "Uninstall Enchant (remove launchers, man pages, and active symlink)?"
    )
    if not cfg.yes and not cfg.dry_run and not typer.confirm(prompt_msg, default=True):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    removed_shims, removed_link, removed_cache, removed_man = uninstall_enchant(cfg, purge=purge)
    console.print(f"Removed {len(removed_shims)} launcher shim(s).")
    if removed_man:
        console.print(f"Removed {len(removed_man)} man page symlink(s).")
    if removed_link:
        console.print(f"Removed active link: {format_path_for_display(removed_link)}")
    if purge:
        console.print(f"Removed {len(removed_cache)} cached item(s).")
    console.print("[bold green]Enchant successfully uninstalled.[/bold green]")


@app.command("which", help="Display active Enchant binary and shims location.")
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Display active Enchant binary and shims location."""
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


@app.command("rehash", help="Regenerate launcher shims and man pages for active version.")
def cmd_rehash(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # pyright: ignore[reportArgumentType]
) -> None:
    """Regenerate launcher shims and man pages for active version."""
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
        err_console.print("[yellow]warning:[/yellow] Enchant is not installed. Nothing to rehash.")
        return

    version_dir = cfg.current_link.resolve()
    created_shims = create_launcher_shims(version_dir, cfg)
    created_man = create_man_links(version_dir, cfg)
    console.print(
        f"Rehashed {len(created_shims)} launcher shim(s) and {len(created_man)} man page(s)."
    )


@app.command(
    "exec",
    help="Run a command with Enchant bin directory prepended to PATH.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@app.command(
    "run",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_exec(
    ctx: typer.Context,
    use: Annotated[
        str | None,
        typer.Option(
            "--use",
            "--use-version",
            help="Run command against a specific version (cached or built on the fly)",
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
    """Run a command with Enchant bin directory prepended to PATH."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    # Reconstruct raw args
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
            "[red]error:[/red] 'exec' requires a command to execute (e.g. 'install-enchant exec enchant-2 -v')"
        )
        raise typer.Exit(1)

    if use_val:
        version_dir = download_and_build_enchant(use_val, cfg)
    else:
        if not cfg.current_link.exists():
            version_dir = download_and_build_enchant("latest", cfg)
            apply_version_link("latest", cfg)
        else:
            version_dir = cfg.current_link.resolve()

    target_bin = version_dir / "bin"
    target_lib = version_dir / "lib"
    new_env = os.environ.copy()
    new_env["PATH"] = f"{target_bin}{os.pathsep}{new_env.get('PATH', '')}"
    if platform.system() == "Darwin":
        new_env["DYLD_LIBRARY_PATH"] = f"{target_lib}:{new_env.get('DYLD_LIBRARY_PATH', '')}"
    else:
        new_env["LD_LIBRARY_PATH"] = f"{target_lib}:{new_env.get('LD_LIBRARY_PATH', '')}"

    try:
        res = subprocess.run(cmd_args, env=new_env, check=False)
        sys.exit(res.returncode)
    except (OSError, subprocess.SubprocessError) as exc:
        err_console.print(f"[red]error:[/red] Failed to execute command: {exc}")
        sys.exit(1)


@app.command(
    "help",
    help="Display help information for Enchant installer or a specific command.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_help(
    ctx: typer.Context,
) -> None:
    """Display CLI help or help for a specific subcommand."""
    render_help(app, ctx.args[0] if ctx.args else None, ctx, "install-enchant")


# Self Command Group
self_app = typer.Typer(
    name="self",
    help="Manage or inspect the installer script itself.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(self_app, name="self")


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
        console.print(f"install_enchant.py (cs1302-code-visualizer {ver})")


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
