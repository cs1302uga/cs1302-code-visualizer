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
"""Java Development Kit (JDK) standalone version and installation manager.

Downloads prebuilt OpenJDK / Eclipse Temurin binaries from the Adoptium REST API
into a cache directory and manages active executables via atomic symlinks and shims.
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
import zipfile
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
from scripts.installer.common import download_file as common_download_file

console = Console()
err_console = Console(stderr=True)

ADOPTIUM_API_BASE = "https://api.adoptium.net/v3"

JDK_KNOWN_BINARIES: frozenset[str] = frozenset({
    "jar",
    "jarsigner",
    "java",
    "javac",
    "javadoc",
    "javap",
    "jcmd",
    "jconsole",
    "jdb",
    "jdeprscan",
    "jdeps",
    "jfr",
    "jhsdb",
    "jimage",
    "jinfo",
    "jlink",
    "jmap",
    "jmod",
    "jpackage",
    "jps",
    "jrunscript",
    "jshell",
    "jstack",
    "jstat",
    "jstatd",
    "keytool",
    "rmiregistry",
    "serialver",
})


def get_min_jdk_version(root_dir: Path) -> str | None:
    """Read minimum JDK version requirement from pyproject.toml.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Configured minimum version string if present, else None.
    """
    return get_min_system_dependency_version(root_dir, "jdk")


def get_platform_os() -> str:
    """Convert platform system name to Adoptium OS parameter.

    Returns:
        Adoptium OS identifier ('mac', 'linux', 'windows').
    """
    sys_name = platform.system()
    if sys_name == "Darwin":
        return "mac"
    if sys_name == "Windows":
        return "windows"
    return "linux"


def get_platform_arch() -> str:
    """Convert platform machine name to Adoptium architecture parameter.

    Returns:
        Adoptium architecture identifier ('aarch64', 'x64').
    """
    mach = platform.machine().lower()
    if mach in ("arm64", "aarch64"):
        return "aarch64"
    return "x64"


@dataclass
class Config:
    """Runtime configuration and filesystem locations.

    Attributes:
        install_dir: Directory containing the active symlink.
        cache_dir: Directory storing versioned installations and downloads.
        bin_dir: Directory containing launcher shims.
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
    def current_link(self) -> Path:
        """Path to the active installation symlink."""
        return self.install_dir / "current"

    @property
    def primary_executable(self) -> Path:
        """Path to the primary 'java' launcher executable."""
        return self.bin_dir / "java"

    def log(self, message: str) -> None:
        """Print verbose log if enabled.

        Args:
            message: Message to log to standard error.
        """
        if self.verbose:
            err_console.print(f"[dim][install_jdk.py][/dim] {message}")


def resolve_default_paths(root_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """Resolve default directories based on the project root directory.

    Args:
        root_dir: Optional root directory of the project.

    Returns:
        A tuple of (default_install_dir, default_cache_dir, default_bin_dir).
    """
    root = root_dir or find_project_root()
    default_install_dir = root / "scripts" / "cache" / "jdk"
    default_cache_dir = root / "scripts" / "cache" / "jdk"
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


def get_java_home(jdk_dir: Path) -> Path:
    """Find the root JAVA_HOME containing bin/java within a JDK directory.

    Args:
        jdk_dir: Directory containing unpacked JDK.

    Returns:
        Path to JAVA_HOME (either Contents/Home or top directory).
    """
    contents_home = jdk_dir / "Contents" / "Home"
    if contents_home.is_dir() and (contents_home / "bin" / "java").exists():
        return contents_home

    if (jdk_dir / "bin" / "java").exists():
        return jdk_dir

    if jdk_dir.is_dir():
        for child in jdk_dir.iterdir():
            if child.is_dir():
                sub_contents = child / "Contents" / "Home"
                if sub_contents.is_dir() and (sub_contents / "bin" / "java").exists():
                    return sub_contents
                if (child / "bin" / "java").exists():
                    return child

    return jdk_dir


def get_installed_version(target: Path | None) -> str | None:
    """Determine the installed JDK version from active target path.

    Args:
        target: Target directory path of the active installation symlink.

    Returns:
        Version string (e.g. '25.0.4+7' or '25.0.0') or None if uninstalled.
    """
    active = get_active_target(target) if target else None
    if not active:
        return None

    name = active.name
    clean_name = clean_version_tag(name)
    if any(c.isdigit() for c in clean_name):
        return clean_name

    java_home = get_java_home(active)
    java_bin = java_home / "bin" / "java"

    if java_bin.exists():
        try:
            res = subprocess.run(
                [str(java_bin), "-version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
            output = res.stderr or res.stdout
            m = re.search(r'version\s+"([^"]+)"', output)
            if m:
                return clean_version_tag(m.group(1))
            m2 = re.search(r"build\s+([0-9.+_-]+)", output)
            if m2:
                return clean_version_tag(m2.group(1))
        except (OSError, subprocess.TimeoutExpired):
            pass

    return None


def get_available_feature_releases(cfg: Config | None = None) -> list[int]:
    """Fetch list of available feature release major versions from Adoptium API.

    Args:
        cfg: Optional runtime configuration.

    Returns:
        List of integer feature versions in ascending order.
    """
    url = f"{ADOPTIUM_API_BASE}/info/available_releases"
    if cfg:
        cfg.log(f"Fetching available releases from {url}")
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                releases = data.get("available_releases", [])
                if isinstance(releases, list):
                    return sorted([
                        int(r) for r in releases if isinstance(r, int) or str(r).isdigit()
                    ])
    except (requests.RequestException, ValueError) as e:
        if cfg:
            cfg.log(f"Adoptium available releases API error: {e}")
    return [8, 11, 17, 21, 25]


def get_latest_adoptium_release(
    feature_version: int = 25,
    cfg: Config | None = None,
) -> dict | None:
    """Fetch latest GA release metadata for a specific feature version.

    Args:
        feature_version: Java major version (e.g. 25, 21).
        cfg: Optional runtime configuration.

    Returns:
        Release dictionary from Adoptium API or None on error.
    """
    os_param = get_platform_os()
    arch_param = get_platform_arch()
    url = (
        f"{ADOPTIUM_API_BASE}/assets/latest/{feature_version}/hotspot"
        f"?os={os_param}&architecture={arch_param}&image_type=jdk&vendor=eclipse"
    )
    if cfg:
        cfg.log(f"Querying Adoptium latest release: {url}")
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict):
                return data
        if cfg:
            cfg.log(f"Adoptium API returned status {resp.status_code}")
    except (requests.RequestException, ValueError) as e:
        if cfg:
            cfg.log(f"Adoptium latest release API error: {e}")
    return None


def get_latest_jdk_version(feature_version: int = 25) -> str | None:
    """Fetch the latest version string for a feature version or overall latest.

    Args:
        feature_version: Major version to check. Defaults to 25.

    Returns:
        Clean version tag (e.g. '25.0.4+7' or '25.0.0') or None on failure.
    """
    release = get_latest_adoptium_release(feature_version)
    if release:
        if "release_name" in release:
            return clean_version_tag(str(release["release_name"]))
        ver_info = release.get("version", {})
        if isinstance(ver_info, dict) and "semver" in ver_info:
            return clean_version_tag(str(ver_info["semver"]))
    return f"{feature_version}.0.0"


def resolve_target_tag(tag: str, cfg: Config) -> tuple[str, str, int]:
    """Resolve requested version tag to clean version, release tag, and major version.

    Args:
        tag: Target version or 'latest'.
        cfg: Runtime configuration.

    Returns:
        Tuple of (clean_version_str, raw_release_name, major_version_int).
    """
    root = find_project_root()
    min_ver = get_min_jdk_version(root)
    default_major = (
        int(min_ver.split(".")[0]) if (min_ver and min_ver.split(".")[0].isdigit()) else 25
    )

    cleaned = clean_version_tag(tag)
    if cleaned.lower() in ("latest", "default"):
        rel = get_latest_adoptium_release(default_major, cfg)
        if rel:
            rel_name = str(rel.get("release_name", f"jdk-{default_major}"))
            clean_ver = clean_version_tag(rel_name)
            return clean_ver, rel_name, default_major
        return f"{default_major}.0.0", f"jdk-{default_major}", default_major

    if cleaned.isdigit():
        major = int(cleaned)
        rel = get_latest_adoptium_release(major, cfg)
        if rel:
            rel_name = str(rel.get("release_name", f"jdk-{major}"))
            clean_ver = clean_version_tag(rel_name)
            return clean_ver, rel_name, major
        return f"{major}.0.0", f"jdk-{major}", major

    major = default_major
    m = re.match(r"^(\d+)", cleaned)
    if m:
        major = int(m.group(1))

    return cleaned, f"jdk-{cleaned}", major


def find_download_asset_url(
    release_data: dict,
    cfg: Config,
) -> tuple[str | None, str | None]:
    """Extract download URL and filename from Adoptium release dictionary.

    Args:
        release_data: Release dictionary from Adoptium API.
        cfg: Runtime configuration.

    Returns:
        Tuple of (download_url, archive_name) or (None, None).
    """
    binary = release_data.get("binary", {})
    package = binary.get("package", {})
    if isinstance(package, dict) and package.get("link"):
        url = str(package["link"])
        name = str(package.get("name", url.split("/")[-1]))
        cfg.log(f"Found Adoptium package: {name} at {url}")
        return url, name

    return None, None


def download_file(url: str, target_file: Path, cfg: Config) -> bool:
    """Download remote file to target path.

    Args:
        url: Remote URL.
        target_file: Local destination path.
        cfg: Runtime configuration.

    Returns:
        True if download succeeded, False otherwise.
    """
    return common_download_file(
        url=url,
        dest_path=target_file,
        description=f"Downloading {target_file.name}",
        dry_run=cfg.dry_run,
        verbose=cfg.verbose,
    )


def unpack_archive(archive_path: Path, target_dir: Path, cfg: Config) -> None:
    """Unpack a zip or tar.gz archive into target directory.

    Args:
        archive_path: Path to archive file.
        target_dir: Target directory.
        cfg: Runtime configuration.
    """
    cfg.log(f"Extracting {archive_path} to {target_dir}...")
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_extract = Path(tempfile.mkdtemp(dir=target_dir.parent, prefix=".extract."))

    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    extracted_path = Path(zf.extract(member, temp_extract))
                    mode = member.external_attr >> 16
                    if mode:
                        if stat.S_ISLNK(mode):
                            try:
                                link_target = extracted_path.read_text(encoding="utf-8").strip()
                                extracted_path.unlink()
                                extracted_path.symlink_to(link_target)
                            except (OSError, UnicodeDecodeError):  # pragma: no cover
                                pass
                        else:
                            try:
                                extracted_path.chmod(mode)
                            except OSError:  # pragma: no cover
                                pass
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as tf:
                tf.extractall(temp_extract)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path.name}")

        extracted_items = list(temp_extract.iterdir())
        if (
            len(extracted_items) == 1
            and extracted_items[0].is_dir()
            and (
                (extracted_items[0] / "bin").is_dir() or (extracted_items[0] / "Contents").is_dir()
            )
        ):
            src_dir = extracted_items[0]
        else:
            src_dir = temp_extract

        for item in src_dir.iterdir():
            dest = target_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

        java_home = get_java_home(target_dir)
        bin_dir = java_home / "bin"
        if bin_dir.is_dir():
            for binary in bin_dir.iterdir():
                if binary.is_file():
                    try:
                        binary.chmod(
                            binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                        )
                    except OSError:  # pragma: no cover
                        pass
    finally:
        shutil.rmtree(temp_extract, ignore_errors=True)


def download_and_install_version(
    tag: str,
    cfg: Config,
) -> Path:
    """Download and unpack a JDK release for the current platform.

    Args:
        tag: Version string or 'latest'.
        cfg: Runtime configuration.

    Returns:
        Path to unpacked version directory in cache.
    """
    clean_tag, raw_tag, major_ver = resolve_target_tag(tag, cfg)
    version_dir = cfg.cache_dir / clean_tag

    if not cfg.force and version_dir.exists():
        cfg.log(f"Using cached version directory: {version_dir}")
        return version_dir

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would download and unpack OpenJDK v{clean_tag} to {format_path_for_display(version_dir)}[/yellow]"
        )
        return version_dir

    release = get_latest_adoptium_release(major_ver, cfg)
    asset_url: str | None = None
    asset_name: str | None = None

    if release:
        asset_url, asset_name = find_download_asset_url(release, cfg)

    if not asset_url:
        os_name = get_platform_os()
        arch = get_platform_arch()
        ext = "zip" if os_name == "windows" else "tar.gz"
        asset_name = f"OpenJDK{major_ver}U-jdk_{arch}_{os_name}_hotspot_{clean_tag}.{ext}"
        asset_url = f"https://github.com/adoptium/temurin{major_ver}-binaries/releases/download/{raw_tag}/{asset_name}"

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    archive_file = cfg.cache_dir / f"jdk-{clean_tag}-{asset_name}"

    if not archive_file.is_file() or cfg.force:
        success = download_file(asset_url, archive_file, cfg)
        if not success:
            err_console.print(f"[red]error:[/red] Failed to download JDK asset from {asset_url}")
            raise typer.Exit(1)

    with err_console.status(
        f"[bold cyan]Unpacking OpenJDK v{clean_tag}...[/bold cyan]",
        spinner="dots",
    ):
        if version_dir.exists():
            shutil.rmtree(version_dir)
        unpack_archive(archive_file, version_dir, cfg)

    return version_dir


def create_shims_for_version(target_dir: Path, cfg: Config) -> list[str]:
    """Generate wrapper shims in bin_dir for all JDK executables.

    Args:
        target_dir: Active installation directory.
        cfg: Runtime configuration.

    Returns:
        List of generated shim executable names.
    """
    java_home = get_java_home(target_dir)
    bin_dir = java_home / "bin" if (java_home / "bin").is_dir() else target_dir

    shims_created: list[str] = []
    if cfg.dry_run:
        return ["java", "javac", "javadoc", "jar", "jshell"]

    cfg.bin_dir.mkdir(parents=True, exist_ok=True)

    if bin_dir.is_dir():
        for item in bin_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                try:
                    item.chmod(item.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except OSError:  # pragma: no cover
                    pass
                name = item.name
                shim_path = cfg.bin_dir / name
                content = f"""#!/usr/bin/env bash
#
# JDK launcher wrapper generated by install-jdk
set -euo pipefail

JDK_ROOT="{cfg.current_link}"
BINARY_NAME="{name}"

if [[ -d "${{JDK_ROOT}}/Contents/Home" ]]; then
    JAVA_HOME="${{JDK_ROOT}}/Contents/Home"
else
    JAVA_HOME="${{JDK_ROOT}}"
fi

BINARY_PATH="${{JAVA_HOME}}/bin/${{BINARY_NAME}}"

if [[ ! -x "${{BINARY_PATH}}" ]]; then
    printf "error: JDK binary '%s' not found at %s. Please run install-jdk to reinstall.\\n" "${{BINARY_NAME}}" "${{BINARY_PATH}}" >&2
    exit 1
fi

export JAVA_HOME
export PATH="${{JAVA_HOME}}/bin:${{PATH}}"

exec "${{BINARY_PATH}}" "$@"
"""
                shim_path.write_text(content, encoding="utf-8")
                shim_path.chmod(0o755)
                shims_created.append(name)

    return shims_created


def apply_version_link(
    tag: str,
    cfg: Config,
    is_explicit_use: bool = False,
) -> Path:
    """Activate a version by updating current symlink and shims.

    Args:
        tag: Version string to link.
        cfg: Runtime configuration.
        is_explicit_use: Whether invoked by 'use' command.

    Returns:
        Path to active version directory.
    """
    version_dir = download_and_install_version(tag, cfg)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would link {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}[/yellow]"
        )
        return version_dir

    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    if cfg.current_link.is_symlink() or cfg.current_link.exists():
        cfg.current_link.unlink()

    cfg.current_link.symlink_to(version_dir)
    shims = create_shims_for_version(version_dir, cfg)
    java_home = get_java_home(version_dir)

    console.print()
    console.print("[bold green]JDK successfully configured![/bold green]")
    console.print(f"  Installed Path: {format_path_for_display(version_dir)}")
    console.print(f"  JAVA_HOME:      {format_path_for_display(java_home)}")
    console.print(
        f"  Active Link:    {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}"
    )
    console.print(
        f"  Created Shims:  {len(shims)} binaries in {format_path_for_display(cfg.bin_dir)}"
    )

    path_env = os.environ.get("PATH", "")
    bin_str = str(cfg.bin_dir)
    if bin_str not in path_env.split(os.pathsep):
        disp_bin = format_path_for_display(cfg.bin_dir)
        console.print()
        console.print("=" * 72)
        console.print(f"[bold yellow]NOTE:[/bold yellow] '{disp_bin}' is not in your current PATH.")
        console.print()
        console.print(
            "To use 'java' and JDK tools directly from your terminal, add it to your PATH:"
        )
        console.print()
        console.print(f'  export PATH="{disp_bin}:$PATH"')
        console.print()
        console.print("To persist this change across shell sessions, add that line to your")
        console.print("shell configuration file (e.g. ~/.bashrc or ~/.zshrc).")
        console.print("=" * 72)
    console.print()
    return version_dir


def clean_cache(cfg: Config) -> int:
    """Remove inactive cached version directories and temporary files.

    Args:
        cfg: Runtime configuration.

    Returns:
        Number of removed directories and files.
    """
    removed_count = 0
    active_target = get_active_target(cfg.current_link)

    if not cfg.cache_dir.is_dir():
        return 0

    for item in cfg.cache_dir.iterdir():
        if item.name == "current" or item.name.startswith("."):
            continue
        is_active = active_target and (
            active_target == item
            or active_target.name == item.name
            or active_target.resolve() == item.resolve()
        )
        if not is_active:
            cfg.log(f"Removing inactive cache item: {item}")
            if not cfg.dry_run:
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            removed_count += 1

    return removed_count


def uninstall_jdk(
    cfg: Config,
    purge: bool = False,
) -> tuple[list[Path], Path | None, list[Path]]:
    """Uninstall JDK by removing launcher shims, active link, and optionally caches.

    Args:
        cfg: Runtime configuration.
        purge: Whether to remove cached versions and archives as well.

    Returns:
        A tuple of (removed_shims, removed_symlink, removed_cache_items).
    """
    removed_shims: list[Path] = []
    removed_link: Path | None = None
    removed_cache: list[Path] = []

    if cfg.bin_dir.is_dir():
        for item in cfg.bin_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                is_shim = False
                if item.name in JDK_KNOWN_BINARIES:
                    is_shim = True
                else:
                    try:
                        header = item.read_text(encoding="utf-8", errors="ignore")[:200]
                        if "install-jdk" in header or "JDK_ROOT" in header:
                            is_shim = True
                    except OSError:  # pragma: no cover
                        pass
                if is_shim:
                    removed_shims.append(item)
                    if not cfg.dry_run:
                        try:
                            item.unlink()
                        except OSError:  # pragma: no cover
                            pass

    if cfg.current_link.is_symlink() or cfg.current_link.exists():
        removed_link = cfg.current_link
        if not cfg.dry_run:
            try:
                cfg.current_link.unlink()
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

    return removed_shims, removed_link, removed_cache


def render_which(cfg: Config) -> None:
    """Print location of active Java binary, JAVA_HOME, and launcher shims.

    Args:
        cfg: Runtime configuration.
    """
    active_target = get_active_target(cfg.current_link)
    java_home = get_java_home(active_target) if active_target else None
    java_bin = (java_home / "bin" / "java") if java_home else None

    console.print("[bold]JDK Locations:[/bold]")
    if java_bin and java_bin.exists():
        console.print(f"  Active Binary: {format_path_for_display(java_bin)}")
    else:
        console.print("  Active Binary: [red]none (not installed or unlinked)[/red]")

    if java_home and java_home.exists():
        console.print(f"  JAVA_HOME:     {format_path_for_display(java_home)}")
    else:
        console.print("  JAVA_HOME:     [red]none[/red]")

    if active_target:
        console.print(f"  Symlink:       {format_path_for_display(active_target)}")
    else:
        console.print("  Symlink:       [red]none[/red]")

    if cfg.primary_executable.exists():
        console.print(f"  Launcher:      {format_path_for_display(cfg.primary_executable)}")
    else:
        console.print("  Launcher:      [red]none (shim missing)[/red]")

    path_env = os.environ.get("PATH", "").split(os.pathsep)
    if str(cfg.bin_dir) in path_env or str(cfg.bin_dir.resolve()) in path_env:
        console.print("  PATH Status:   [green]Launcher directory is in PATH[/green]")
    else:
        console.print(
            f"  PATH Status:   [yellow]Launcher directory is NOT in PATH ({format_path_for_display(cfg.bin_dir)})[/yellow]"
        )


def create_transient_shim(
    target_version_dir: Path,
    cache_dir: Path,
    cfg: Config,
) -> tuple[Path, Path]:
    """Create a temporary execution shim pointing to target_version_dir.

    Args:
        target_version_dir: Directory of the version to execute against.
        cache_dir: Cache directory.
        cfg: Runtime configuration.

    Returns:
        Tuple of (temp_bin_dir, path_to_transient_java).
    """
    tmp_bin = Path(tempfile.mkdtemp(prefix="jdk_exec_"))
    java_home = get_java_home(target_version_dir)
    java_shim = tmp_bin / "java"
    bin_dir = java_home / "bin" if (java_home / "bin").is_dir() else target_version_dir

    for item in bin_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            s_path = tmp_bin / item.name
            content = f"""#!/usr/bin/env bash
set -euo pipefail
JAVA_HOME="{java_home.resolve()}"
BINARY_PATH="{item.resolve()}"
export JAVA_HOME
export PATH="${{JAVA_HOME}}/bin:${{PATH}}"
exec "${{BINARY_PATH}}" "$@"
"""
            s_path.write_text(content, encoding="utf-8")
            s_path.chmod(0o755)

    return tmp_bin, java_shim


def run_exec_command(
    command_args: list[str],
    bin_dir_to_use: Path,
    temp_dir_to_cleanup: Path | None,
    cfg: Config,
) -> None:
    """Execute a shell command with JDK bin directory prepended to PATH.

    Args:
        command_args: Command and arguments to execute.
        bin_dir_to_use: Directory containing executables to prepend to PATH.
        temp_dir_to_cleanup: Temporary directory to clean up after execution.
        cfg: Runtime configuration.

    Raises:
        typer.Exit: Exits with command's return code.
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
    name=Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-jdk",
    help="Manages Java Development Kit (JDK) binaries, cache storage, and executable shims.",
    no_args_is_help=True,
    add_completion=False,
)


def cli_version_callback(value: bool) -> None:
    """Print version string and exit."""
    if value:
        root = find_project_root()
        ver = get_project_version(root)
        console.print(f"install_jdk.py (cs1302-book {ver})")
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


@app.command("install", help="Install specified (or default 25) JDK release into cache and link.")
def cmd_install(
    tag: Annotated[
        str,
        typer.Argument(
            help="JDK version to install (e.g. '25', '21', 'latest')",
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
    """Install specified (or latest) JDK release into cache and link shims."""
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
    clean_tag, _, _ = resolve_target_tag(tag, cfg)
    version_dir = cfg.cache_dir / clean_tag

    if not cfg.yes and not cfg.dry_run:
        prompt = f"Install and activate OpenJDK v{clean_tag}?"
        if not typer.confirm(prompt, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    if version_dir.exists() and not cfg.force:
        console.print(f"Using existing cached version: {format_path_for_display(version_dir)}")

    apply_version_link(tag, cfg, is_explicit_use=False)


@app.command("update", help="Check Adoptium and update to the latest release for target JDK.")
def cmd_update(
    major_version: Annotated[
        int,
        typer.Option(
            "--major",
            "-m",
            help="Major JDK version to update (defaults to 25)",
        ),
    ] = 25,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Check Adoptium and update to the latest release."""
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
    current_ver = get_installed_version(cfg.current_link)
    latest_ver = get_latest_jdk_version(major_version)

    if not latest_ver:
        err_console.print(
            f"[red]error:[/red] Unable to retrieve latest JDK {major_version} release from Adoptium."
        )
        raise typer.Exit(1)

    if current_ver and is_version_ge(current_ver, latest_ver) and not cfg.force:
        console.print(f"JDK is already up to date ({current_ver}).")
        return

    if not cfg.yes and not cfg.dry_run:
        prompt = (
            f"Update JDK from {current_ver or 'none'} to {latest_ver}?"
            if current_ver
            else f"Install latest JDK {major_version} release (v{latest_ver})?"
        )
        if not typer.confirm(prompt, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    apply_version_link(str(major_version), cfg, is_explicit_use=False)


@app.command("use", help="Switch active version to TAG (downloads to cache if missing).")
def cmd_use(
    tag: Annotated[str, typer.Argument(help="JDK version tag to activate (e.g. '25', '21')")],
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


@app.command("versions", help="List all downloaded cached JDK versions and mark active link.")
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
    """List all downloaded cached JDK versions and mark active link."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    active_target = get_active_target(cfg.current_link)
    installed_versions: list[tuple[str, bool]] = []

    if cfg.cache_dir.is_dir():
        for item in sorted(cfg.cache_dir.iterdir()):
            if item.name == "current" or item.name.startswith("."):
                continue
            if item.is_dir():
                clean_tag = clean_version_tag(item.name)
                is_active = active_target and (
                    active_target == item
                    or active_target.name == item.name
                    or active_target.resolve() == item.resolve()
                )
                installed_versions.append((clean_tag, bool(is_active)))

    if not installed_versions:
        console.print("No JDK versions currently installed in cache.")
        return

    table = Table(title="Installed JDK Versions", box=None)
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="green")

    for ver, active in installed_versions:
        status_str = "* active" if active else ""
        table.add_row(ver, status_str)

    console.print(table)


@app.command("status", help="Display current JDK version, latest release, and paths.")
def cmd_status(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display current JDK version, latest release, and paths."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    root = find_project_root()
    min_ver = get_min_jdk_version(root)
    default_major = (
        int(min_ver.split(".")[0]) if (min_ver and min_ver.split(".")[0].isdigit()) else 25
    )

    installed_ver = get_installed_version(cfg.current_link)
    with err_console.status(
        f"[bold cyan]Checking latest Adoptium OpenJDK {default_major} release...[/bold cyan]",
        spinner="dots",
    ):
        latest_ver = get_latest_jdk_version(default_major)

    console.print("[bold]JDK Installation Status:[/bold]")
    console.print(f"  Active version:       {installed_ver or 'none (not installed)'}")
    console.print(f"  Latest Adoptium tag:  {latest_ver or 'unknown'}")
    if min_ver:
        console.print(f"  Project min version:  {min_ver}")

    console.print()
    if not installed_ver:
        console.print(
            "[yellow]Status: JDK is not installed. Run 'install-jdk install' to install.[/yellow]"
        )
    elif latest_ver and is_version_ge(installed_ver, latest_ver):
        console.print("[green]Status: JDK is up to date.[/green]")
    elif latest_ver and not is_version_ge(installed_ver, latest_ver):
        console.print(
            f"[yellow]Status: Update available ({installed_ver} -> {latest_ver}). Run 'install-jdk update' to upgrade.[/yellow]"
        )
    elif min_ver and not is_version_ge(installed_ver, min_ver):
        console.print(
            f"[red]Status: Installed version ({installed_ver}) does not satisfy project min requirement (>={min_ver}).[/red]"
        )


@app.command("clean", help="Remove cached JDK versions that are not currently active.")
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
    """Remove cached JDK versions that are not currently active."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    active_target = get_active_target(cfg.current_link)
    unused_items: list[Path] = []
    if cfg.cache_dir.is_dir():
        for item in cfg.cache_dir.iterdir():
            if item.name == "current" or item.name.startswith("."):
                continue
            is_active = active_target and (
                active_target == item
                or active_target.name == item.name
                or active_target.resolve() == item.resolve()
            )
            if not is_active:
                unused_items.append(item)

    if not unused_items:
        console.print("No unused cached versions found.")
        return

    if (
        not cfg.yes
        and not cfg.dry_run
        and not typer.confirm(f"Remove {len(unused_items)} unused cached version(s)?", default=True)
    ):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Scanning unused JDK cache in {format_path_for_display(cfg.cache_dir)}...[/yellow]"
        )
    else:
        console.print(f"Cleaning unused JDK cache in {format_path_for_display(cfg.cache_dir)}...")

    removed = clean_cache(cfg)

    if cfg.dry_run:
        console.print(f"[yellow]\\[dry-run] Would remove {removed} unused version(s).[/yellow]")
    else:
        console.print(f"Done. Removed {removed} unused version(s).")


@app.command("uninstall", help="Uninstall JDK shims and active installation.")
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
    """Uninstall JDK by removing launcher shims and active link."""
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
        "Uninstall JDK and remove all cached downloads?"
        if purge
        else "Uninstall JDK (remove launchers and active symlink)?"
    )
    if not cfg.yes and not cfg.dry_run and not typer.confirm(prompt_msg, default=True):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    if cfg.dry_run:
        console.print("[yellow]\\[dry-run] Simulating JDK uninstallation...[/yellow]")
    else:
        console.print("Uninstalling JDK...")

    removed_shims, removed_link, removed_cache = uninstall_jdk(cfg, purge=purge)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would remove {len(removed_shims)} launcher shim(s)[/yellow]"
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
        console.print(f"Removed {len(removed_shims)} launcher shim(s).")
        if removed_link:
            console.print(f"Removed active link: {format_path_for_display(removed_link)}")
        if purge:
            console.print(f"Removed {len(removed_cache)} cached item(s).")
        console.print("[bold green]JDK successfully uninstalled.[/bold green]")


@app.command(
    "which", help="Display active Java binary path, JAVA_HOME, and launcher shims location."
)
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display active Java binary path, JAVA_HOME, and launcher shims location."""
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
    help="Run a command with JDK bin directory prepended to PATH and JAVA_HOME set.",
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
            help="Run command against a specific JDK version (cached or downloaded on the fly)",
        ),
    ] = None,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Run a command with JDK bin directory prepended to PATH."""
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
        clean_tag, _, _ = resolve_target_tag(use, cfg)
        target_dir = cfg.cache_dir / clean_tag
        if not target_dir.exists():
            download_and_install_version(use, cfg)

        tmp_dir, _ = create_transient_shim(target_dir, cfg.cache_dir, cfg)
        run_exec_command(extra_args, tmp_dir, tmp_dir, cfg)
    else:
        if not cfg.primary_executable.exists():
            apply_version_link("latest", cfg, is_explicit_use=False)
        run_exec_command(extra_args, cfg.bin_dir, None, cfg)


@app.command(
    "rehash",
    help="Clear and regenerate JDK shims in scripts/installer/shims/bin (or custom bin-dir).",
)
def cmd_rehash(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Clear and rebuild JDK executable shims."""
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
    active_target = get_active_target(cfg.current_link)
    if not active_target:
        console.print(
            "[yellow]JDK is not currently installed or linked. Run 'install-jdk install' first.[/yellow]"
        )
        return

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would clear and recreate JDK shims in {format_path_for_display(cfg.bin_dir)}[/yellow]"
        )
        return

    if cfg.bin_dir.is_dir():
        for item in cfg.bin_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                is_jdk = False
                if item.name in JDK_KNOWN_BINARIES:
                    is_jdk = True
                else:
                    try:
                        header = item.read_text(encoding="utf-8", errors="ignore")[:200]
                        if "install-jdk" in header or "JDK_ROOT" in header:
                            is_jdk = True
                    except OSError:  # pragma: no cover
                        pass
                if is_jdk:
                    try:
                        item.unlink()
                    except OSError:  # pragma: no cover
                        pass

    shims = create_shims_for_version(active_target, cfg)
    console.print(
        f"[bold green]Rehashed {len(shims)} JDK shim(s) in {format_path_for_display(cfg.bin_dir)}.[/bold green]"
    )


@app.command("help", help="Display help information for JDK installer or a specific command.")
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
    """Display help information for JDK installer or a specific command."""
    cli_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-jdk"
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
        console.print(f"install_jdk.py (cs1302-book {ver})")


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
