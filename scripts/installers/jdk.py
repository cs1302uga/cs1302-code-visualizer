#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "click>=8.0.0",
#     "packaging>=24.0",
#     "platformdirs>=4.0.0",
#     "requests>=2.31.0",
#     "rich>=13.7.0",
#     "typer>=0.12.0",
# ]
# ///
"""JDK version and installation manager.

Downloads versioned Java Development Kits (JDKs) from Eclipse Adoptium (Temurin)
into a local cache directory, verifies checksums, and manages the active JDK
installation via an atomic symlink and launcher wrappers.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import click
import requests
import typer
from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import Version
from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

DEFAULT_REQUEST_TIMEOUT = 30.0
DOWNLOAD_CHUNK_SIZE = 64 * 1024


def find_project_root(start_dir: Path | None = None) -> Path:
    """Locate the project root directory containing pyproject.toml.

    Args:
        start_dir: Optional starting directory. Defaults to script directory.

    Returns:
        Path to directory containing pyproject.toml, or cwd if not found.
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
        Version string from pyproject.toml, or '0.1.0' as fallback.
    """
    toml_path = root_dir / "pyproject.toml"
    if toml_path.is_file():
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
                return str(data.get("project", {}).get("version", "0.1.0"))
        except (OSError, tomllib.TOMLDecodeError):
            return "0.1.0"
    return "0.1.0"


def get_min_jdk_version(root_dir: Path) -> str | None:
    """Read configured minimum JDK version from pyproject.toml if specified.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Configured version string (e.g. '21'), or None.
    """
    toml_path = root_dir / "pyproject.toml"
    if not toml_path.is_file():
        return None
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
            # Check system-dependencies list
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
                except InvalidRequirement:
                    continue
                if req.name in ("jdk", "java", "openjdk"):
                    for spec in req.specifier:
                        if spec.operator in (">=", "=="):
                            return spec.version
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return "21"


@dataclass
class Config:
    """Runtime configuration and filesystem locations.

    Attributes:
        install_dir: Directory containing the active symlink.
        cache_dir: Directory storing versioned JDKs.
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
    def jdk_symlink(self) -> Path:
        """Path to the active JDK symlink."""
        return self.install_dir / "jdk"

    @property
    def java_launcher(self) -> Path:
        """Path to the executable java launcher shim."""
        return self.bin_dir / "java"

    @property
    def javac_launcher(self) -> Path:
        """Path to the executable javac launcher shim."""
        return self.bin_dir / "javac"

    def log(self, message: str) -> None:
        """Print verbose log message if enabled.

        Args:
            message: Message string to log to standard error.
        """
        if self.verbose:
            err_console.print(f"[dim][install-jdk.py][/dim] {message}")


def resolve_default_paths(root_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """Resolve default directory locations based on environment and project structure.

    Args:
        root_dir: Optional project root directory.

    Returns:
        Tuple of (default_install_dir, default_cache_dir, default_bin_dir).
    """
    root = root_dir or find_project_root()
    if (root / "scripts").is_dir():
        default_install_dir = root / "scripts" / "cache"
        default_cache_dir = root / "scripts" / "cache" / "jdks"
        default_bin_dir = root / "scripts" / "shims" / "bin"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        default_install_dir = (
            Path(xdg_data) / "cs1302-code-visualizer"
            if xdg_data
            else Path.home() / ".local" / "share" / "cs1302-code-visualizer"
        )
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        default_cache_dir = (
            Path(xdg_cache) / "cs1302-code-visualizer" / "jdks"
            if xdg_cache
            else Path.home() / ".cache" / "cs1302-code-visualizer" / "jdks"
        )
        default_bin_dir = Path.home() / ".local" / "bin"

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
    """Create a Config object respecting environment variables and CLI overrides.

    Args:
        dir_path: Custom installation directory.
        cache_dir: Custom cache directory.
        bin_dir: Custom binary directory.
        verbose: Verbose flag from CLI.
        dry_run: Dry-run flag from CLI.
        force: Force flag from CLI.
        yes: Automatic yes flag from CLI.

    Returns:
        Configured Config instance.
    """
    root = find_project_root()
    default_install, default_cache, default_bin = resolve_default_paths(root)

    if "JDK_INSTALL_DIR" in os.environ:
        default_install = Path(os.environ["JDK_INSTALL_DIR"])
    if "JDK_CACHE_DIR" in os.environ:
        default_cache = Path(os.environ["JDK_CACHE_DIR"])
    if "JDK_BIN_DIR" in os.environ:
        default_bin = Path(os.environ["JDK_BIN_DIR"])

    env_verbose = os.environ.get("VERBOSE", "0")
    is_verbose = verbose or (env_verbose not in ("0", "", "false", "False"))

    return Config(
        install_dir=dir_path or default_install,
        cache_dir=cache_dir or default_cache,
        bin_dir=bin_dir or default_bin,
        verbose=is_verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )


def format_path_for_display(path: Path | str | None) -> str:
    """Format a path replacing the user's home directory prefix with '~'.

    Args:
        path: Path or string to format.

    Returns:
        Formatted path string with '~' prefix if under home directory, or 'none'.
    """
    if path is None:
        return "none"
    p = Path(path).expanduser()
    try:
        home = Path.home()
        if not p.is_absolute():
            p = p.absolute()
        if p == home:
            return "~"
        if p.is_relative_to(home):
            rel = p.relative_to(home)
            return f"~/{rel}"
    except (ValueError, RuntimeError):
        pass
    return str(p)


def detect_os_and_arch() -> tuple[str, str]:
    """Detect the current operating system and architecture for Adoptium downloads.

    Returns:
        Tuple of (os_name, arch_name) compatible with Adoptium API.

    Raises:
        typer.Exit: If OS or architecture is unsupported.
    """
    system_name = platform.system()
    match system_name:
        case "Linux":
            os_name = "linux"
        case "Windows":
            os_name = "windows"
        case "Darwin":
            os_name = "mac"
        case other:
            err_console.print(f"[red]error:[/red] Unsupported operating system: {other}")
            raise typer.Exit(1)

    machine_name = platform.machine().lower()
    match machine_name:
        case "amd64" | "x86_64" | "x64":
            arch_name = "x64"
        case "aarch64" | "arm64":
            arch_name = "aarch64"
        case other:
            err_console.print(f"[red]error:[/red] Unsupported architecture: {other} for {os_name}")
            raise typer.Exit(1)

    return os_name, arch_name


def find_java_home_in_jdk_dir(jdk_dir: Path) -> Path | None:
    """Locate the actual JAVA_HOME directory containing bin/java within a JDK folder.

    Args:
        jdk_dir: Root directory of extracted JDK.

    Returns:
        Path to JAVA_HOME if valid, else None.
    """
    if not jdk_dir.is_dir():
        return None

    # Check direct layout (Linux / Windows / stripped macOS)
    if (jdk_dir / "bin" / "java").is_file() or (jdk_dir / "bin" / "java.exe").is_file():
        return jdk_dir

    # Check macOS bundle layout (Contents/Home)
    mac_home = jdk_dir / "Contents" / "Home"
    if (mac_home / "bin" / "java").is_file():
        return mac_home

    # Check for single nested subdirectory containing bin/java or Contents/Home
    subdirs = [p for p in jdk_dir.iterdir() if p.is_dir()]
    if len(subdirs) == 1:
        nested = subdirs[0]
        if (nested / "bin" / "java").is_file() or (nested / "bin" / "java.exe").is_file():
            return nested
        nested_mac = nested / "Contents" / "Home"
        if (nested_mac / "bin" / "java").is_file():
            return nested_mac

    return None


def get_active_target(jdk_symlink: Path) -> Path | None:
    """Return the resolved target Path if the symlink exists.

    Args:
        jdk_symlink: Path to the active symlink.

    Returns:
        Target Path if existing, else None.
    """
    if jdk_symlink.is_symlink():
        try:
            target = os.readlink(jdk_symlink)
            return Path(target)
        except OSError:
            return None
    if jdk_symlink.is_dir():
        return jdk_symlink
    return None


def get_installed_java_version(java_home: Path | None) -> str | None:
    """Extract full Java version string by running java -version in java_home.

    Args:
        java_home: Path to JAVA_HOME directory.

    Returns:
        Parsed Java version string (e.g. '21.0.2'), or None.
    """
    if not java_home or not java_home.is_dir():
        return None

    java_bin = java_home / "bin" / "java"
    if not java_bin.is_file():
        java_bin = java_home / "bin" / "java.exe"
    if not java_bin.is_file():
        return None

    try:
        res = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = res.stderr or res.stdout
        if output:
            for line in output.splitlines():
                if "version" in line:
                    match = re.search(r'version "([^"]+)"', line)
                    if match:
                        return match.group(1)
                    match_open = re.search(r"openjdk (\d+[\.\d_+]*)", line)
                    if match_open:
                        return match_open.group(1)
    except (OSError, subprocess.SubprocessError):
        return None

    return None


def get_latest_adoptium_lts() -> str:
    """Query the Adoptium API for the most recent LTS JDK major version.

    Returns:
        Major version number string (e.g. '21' or '25').
    """
    try:
        resp = requests.get(
            "https://api.adoptium.net/v3/info/available_releases",
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            lts_num = data.get("most_recent_lts")
            if lts_num:
                return str(lts_num)
    except (requests.RequestException, ValueError):
        pass
    return "21"


def resolve_jdk_release_metadata(
    requested_version: str,
    os_name: str,
    arch_name: str,
    cfg: Config,
) -> dict[str, Any]:
    """Resolve download URL, expected checksum, and release tags from Adoptium API.

    Args:
        requested_version: Version tag, major version (e.g. '21'), 'latest', or 'lts'.
        os_name: Operating system name ('linux', 'mac', 'windows').
        arch_name: Architecture name ('x64', 'aarch64').
        cfg: Runtime configuration.

    Returns:
        Dictionary with 'download_url', 'sha256', 'release_name', and 'semver'.

    Raises:
        typer.Exit: If release cannot be resolved.
    """
    tag = requested_version.strip()
    if tag.lower() in ("latest", "lts"):
        major_ver = get_latest_adoptium_lts()
        cfg.log(f"Resolved '{tag}' to major LTS release {major_ver}")
    elif tag.isdigit():
        major_ver = tag
    else:
        # Extract major version number if full semver was given
        match = re.match(r"^(\d+)", tag.lstrip("v").lstrip("jdk-"))
        major_ver = match.group(1) if match else "21"

    cfg.log(f"Querying Adoptium API for JDK {major_ver} on {os_name}/{arch_name}...")

    # Query official feature releases endpoint to get metadata + checksum
    api_url = (
        f"https://api.adoptium.net/v3/assets/feature_releases/{major_ver}/ga"
        f"?os={os_name}&architecture={arch_name}&image_type=jdk&jvm_impl=hotspot"
    )

    try:
        resp = requests.get(api_url, timeout=DEFAULT_REQUEST_TIMEOUT)
        if resp.status_code == 200:
            releases = resp.json()
            if releases and isinstance(releases, list):
                latest_rel = releases[0]
                release_name = latest_rel.get("release_name", f"jdk-{major_ver}")
                semver = latest_rel.get("version_data", {}).get("semver", major_ver)
                binaries = latest_rel.get("binaries", [])
                if binaries:
                    pkg = binaries[0].get("package", {})
                    download_url = pkg.get("link")
                    checksum = pkg.get("checksum")
                    if download_url:
                        return {
                            "download_url": download_url,
                            "sha256": checksum,
                            "release_name": release_name,
                            "semver": semver,
                        }
    except requests.RequestException as exc:
        cfg.log(f"Adoptium API query failed: {exc}")

    # Fallback to direct binary endpoint
    fallback_url = f"https://api.adoptium.net/v3/binary/latest/{major_ver}/ga/{os_name}/{arch_name}/jdk/hotspot/normal/eclipse"
    return {
        "download_url": fallback_url,
        "sha256": None,
        "release_name": f"jdk-{major_ver}",
        "semver": major_ver,
    }


def download_and_extract_jdk(
    requested_version: str,
    cfg: Config,
) -> tuple[Path, Path, str]:
    """Download, verify checksum, and extract a JDK into the cache directory.

    Args:
        requested_version: Version identifier string.
        cfg: Runtime configuration.

    Returns:
        Tuple of (target_cache_dir, java_home_dir, resolved_version_string).

    Raises:
        typer.Exit: If download or extraction fails.
    """
    os_name, arch_name = detect_os_and_arch()
    metadata = resolve_jdk_release_metadata(requested_version, os_name, arch_name, cfg)

    release_name = metadata["release_name"].removeprefix("jdk-")
    clean_tag = f"jdk-{release_name}"
    target_dir = cfg.cache_dir / clean_tag
    cfg.log(f"Target cached JDK directory: {target_dir}")

    # Check if valid cached installation already exists
    if target_dir.is_dir() and not cfg.force:
        java_home = find_java_home_in_jdk_dir(target_dir)
        if java_home and (java_home / "bin" / "java").is_file():
            ver = get_installed_java_version(java_home) or metadata["semver"]
            err_console.print(
                f"Using existing cached JDK: [cyan]{format_path_for_display(target_dir)}[/cyan] (v{ver})"
            )
            return target_dir, java_home, ver

    if cfg.dry_run:
        err_console.print(
            f"[yellow][dry-run][/yellow] Would download and provision {clean_tag} to {format_path_for_display(target_dir)}"
        )
        return target_dir, target_dir, metadata["semver"]

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    download_url = metadata["download_url"]
    expected_sha = metadata.get("sha256")

    # Temp workspace on same filesystem to guarantee atomic mv
    tmp_work_dir = Path(tempfile.mkdtemp(dir=cfg.cache_dir, prefix=".tmp_jdk_"))
    archive_ext = ".zip" if os_name == "windows" else ".tar.gz"
    archive_file = tmp_work_dir / f"jdk_archive{archive_ext}"
    extract_dir = tmp_work_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with err_console.status(
            f"[bold cyan]Downloading JDK {release_name} ({os_name}/{arch_name})...[/bold cyan]",
            spinner="dots",
        ):
            cfg.log(f"Downloading from {download_url}...")
            resp = requests.get(
                download_url,
                stream=True,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()

            sha256_hasher = hashlib.sha256()
            with open(archive_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        _ = f.write(chunk)
                        sha256_hasher.update(chunk)

            computed_sha = sha256_hasher.hexdigest()
            cfg.log(f"Downloaded archive SHA256: {computed_sha}")

            if expected_sha and expected_sha.lower() != computed_sha.lower():
                err_console.print(
                    f"[red]error:[/red] SHA256 checksum mismatch!\n"
                    f"  Expected: {expected_sha}\n"
                    f"  Got:      {computed_sha}"
                )
                raise typer.Exit(1)

        with err_console.status(
            f"[bold cyan]Extracting and verifying JDK {release_name}...[/bold cyan]",
            spinner="dots",
        ):
            if os_name == "windows" or archive_file.name.endswith(".zip"):
                with zipfile.ZipFile(archive_file) as zf:
                    zf.extractall(extract_dir)
            else:
                with tarfile.open(archive_file, mode="r:*") as tf:
                    tf.extractall(extract_dir, numeric_owner=True, filter="tar")

            # If extracted archive has a single top-level directory, promote it
            subdirs = [p for p in extract_dir.iterdir() if p.is_dir()]
            if (
                len(subdirs) == 1
                and not (extract_dir / "bin").is_dir()
                and not (extract_dir / "Contents").is_dir()
            ):
                source_dir = subdirs[0]
            else:
                source_dir = extract_dir

            # Validate extracted directory structure
            java_home = find_java_home_in_jdk_dir(source_dir)
            if not java_home:
                err_console.print(
                    "[red]error:[/red] Extracted archive does not contain a valid JDK layout."
                )
                raise typer.Exit(1)

            # Atomic swap into cache
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            _ = shutil.move(str(source_dir), str(target_dir))

        # Re-resolve JAVA_HOME in final destination
        final_java_home = find_java_home_in_jdk_dir(target_dir)
        if not final_java_home:
            err_console.print(
                "[red]error:[/red] Failed to resolve final JAVA_HOME after extraction."
            )
            raise typer.Exit(1)

        ver = get_installed_java_version(final_java_home) or metadata["semver"]
        err_console.print(
            f"[bold green]Verified JDK installation[/bold green] (version: [cyan]{ver}[/cyan])."
        )
        return target_dir, final_java_home, ver

    finally:
        shutil.rmtree(tmp_work_dir, ignore_errors=True)


def create_launcher_shims(java_home: Path, cfg: Config) -> None:
    """Create executable launcher shims for java, javac, and jshell in bin_dir.

    Args:
        java_home: Path to the active JAVA_HOME directory.
        cfg: Runtime configuration.
    """
    cfg.log(f"Creating launcher shims in {cfg.bin_dir} for JAVA_HOME: {java_home}")
    if cfg.dry_run:
        err_console.print(
            f"[yellow][dry-run][/yellow] Would create launcher shims in {format_path_for_display(cfg.bin_dir)}"
        )
        return

    cfg.bin_dir.mkdir(parents=True, exist_ok=True)
    binaries = ["java", "javac", "jshell", "jar", "javadoc"]

    for bin_name in binaries:
        shim_path = cfg.bin_dir / bin_name
        shim_content = f"""#!/usr/bin/env bash
#
# JDK launcher shim generated by install-jdk.py
set -euo pipefail

JAVA_HOME="{java_home}"
export JAVA_HOME

TARGET_BIN="${{JAVA_HOME}}/bin/{bin_name}"

if [[ ! -f "${{TARGET_BIN}}" ]]; then
    printf "error: JDK binary not found at %s. Please run 'install-jdk.py install' to reinstall.\\n" "${{TARGET_BIN}}" >&2
    exit 1
fi

exec "${{TARGET_BIN}}" "$@"
"""
        shim_path.write_text(shim_content, encoding="utf-8")
        shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def apply_version_link(
    version_tag: str,
    cfg: Config,
    is_explicit_use: bool = False,
) -> None:
    """Provision and link the specified JDK version.

    Args:
        version_tag: Version identifier string.
        cfg: Runtime configuration.
        is_explicit_use: Whether the version was explicitly chosen by user.
    """
    current_target = get_active_target(cfg.jdk_symlink)
    current_ver = get_installed_java_version(current_target)
    cfg.log(f"Current active version: {current_ver or 'none'}, requested: {version_tag}")

    if not cfg.yes and not cfg.dry_run:
        prompt_msg = (
            f"Update active JDK from {current_ver} to {version_tag}?"
            if current_ver and current_ver != version_tag
            else f"Install and activate JDK {version_tag}?"
        )
        if not typer.confirm(prompt_msg, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    _, java_home, resolved_ver = download_and_extract_jdk(version_tag, cfg)

    if cfg.dry_run:
        console.print("\n[bold cyan][dry-run] JDK Execution Plan:[/bold cyan]")
        console.print(f"  Target Version: [green]{version_tag}[/green]")
        console.print(f"  JAVA_HOME:      {format_path_for_display(java_home)}")
        console.print(
            f"  Symlink:        {format_path_for_display(cfg.jdk_symlink)} -> {format_path_for_display(java_home)}"
        )
        console.print(f"  Shims Directory:{format_path_for_display(cfg.bin_dir)}")
        return

    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    if cfg.jdk_symlink.is_symlink():
        cfg.jdk_symlink.unlink()
    elif cfg.jdk_symlink.is_dir():
        shutil.rmtree(cfg.jdk_symlink, ignore_errors=True)
    elif cfg.jdk_symlink.exists():
        cfg.jdk_symlink.unlink()

    cfg.log(f"Symlinking {cfg.jdk_symlink} -> {java_home}")
    cfg.jdk_symlink.symlink_to(java_home)
    create_launcher_shims(java_home, cfg)

    console.print("\n[bold green]JDK successfully configured![/bold green]")
    console.print(f"  Active JAVA_HOME: {format_path_for_display(java_home)}")
    console.print(
        f"  Active Link:      {format_path_for_display(cfg.jdk_symlink)} -> {format_path_for_display(java_home)}"
    )
    console.print(f"  Java Version:     [cyan]{resolved_ver}[/cyan]")
    console.print(f"  Launcher Shims:   {format_path_for_display(cfg.bin_dir)}/java\n")

    current_path = os.environ.get("PATH", "").split(os.pathsep)
    if str(cfg.bin_dir) not in current_path:
        console.print("=" * 72, style="yellow")
        console.print(
            f"NOTE: '{format_path_for_display(cfg.bin_dir)}' is not in your current PATH.\n",
            style="bold yellow",
        )
        console.print("To use 'java' directly from your terminal, add it to your PATH:\n")
        console.print(
            f'  export PATH="{format_path_for_display(cfg.bin_dir)}:$PATH"\n'
            f'  export JAVA_HOME="{format_path_for_display(java_home)}"\n',
            style="bold green",
        )
        console.print(
            "To persist this change across shell sessions, add those lines to your\n"
            "shell configuration file (e.g. ~/.bashrc or ~/.zshrc)."
        )
        console.print("=" * 72 + "\n", style="yellow")


def render_versions_table(cfg: Config) -> None:
    """Render a table of all cached JDK versions.

    Args:
        cfg: Runtime configuration.
    """
    active_target = get_active_target(cfg.jdk_symlink)

    table = Table(title="Cached JDK Versions", box=None)
    table.add_column("", justify="center", style="bold green", width=3)
    table.add_column("Release", style="bold cyan", width=20)
    table.add_column("Java Version", style="green", width=16)
    table.add_column("JAVA_HOME Location", style="dim")

    count = 0
    if cfg.cache_dir.is_dir():
        for jdk_entry in sorted(cfg.cache_dir.glob("jdk-*")):
            if jdk_entry.is_dir():
                java_home = find_java_home_in_jdk_dir(jdk_entry)
                if java_home:
                    count += 1
                    ver = get_installed_java_version(java_home) or "unknown"
                    rel_name = jdk_entry.name.removeprefix("jdk-")
                    is_active = active_target and (
                        active_target == java_home or active_target.resolve() == java_home.resolve()
                    )
                    marker = "*" if is_active else ""
                    table.add_row(
                        marker,
                        rel_name,
                        ver,
                        format_path_for_display(java_home),
                    )

    if count > 0:
        console.print(table)
    else:
        console.print(
            f"  (no cached JDK installations found in {format_path_for_display(cfg.cache_dir)})"
        )

    console.print(
        f"\nActive link: {format_path_for_display(cfg.jdk_symlink)} -> {format_path_for_display(active_target)}"
    )


def render_status(cfg: Config) -> None:
    """Display active JDK status, latest Adoptium LTS release, and path information.

    Args:
        cfg: Runtime configuration.
    """
    with err_console.status(
        "[bold cyan]Checking active JDK and Adoptium LTS status...[/bold cyan]",
        spinner="dots",
    ):
        active_target = get_active_target(cfg.jdk_symlink)
        active_ver = get_installed_java_version(active_target)
        latest_lts = get_latest_adoptium_lts()
        min_ver = get_min_jdk_version(find_project_root())

    console.print("[bold]JDK Installation Status:[/bold]")
    console.print(f"  Active Version:       [cyan]{active_ver or 'none (not installed)'}[/cyan]")
    console.print(f"  Latest Adoptium LTS:  [green]{latest_lts}[/green]")
    if min_ver:
        console.print(f"  Project Min Version:  {min_ver}")
    console.print(f"  Active JAVA_HOME:     {format_path_for_display(active_target)}")
    console.print(f"  Cache Directory:      {format_path_for_display(cfg.cache_dir)}")
    console.print(f"  Launcher Directory:   {format_path_for_display(cfg.bin_dir)}")

    if not active_ver:
        console.print(
            "\n[bold yellow]Status: JDK is not installed. "
            "Run 'install-jdk.py install' to install.[/bold yellow]"
        )
    elif min_ver and int(active_ver.split(".")[0]) < int(min_ver.split(".")[0]):
        console.print(
            f"\n[bold red]Status: Active version ({active_ver}) does not satisfy project minimum requirement ({min_ver}). "
            f"Run 'install-jdk.py install {min_ver}' to upgrade.[/bold red]"
        )
    else:
        console.print("\n[bold green]Status: JDK is active and ready.[/bold green]")


def clean_cache(cfg: Config) -> int:
    """Remove cached JDK installations that are not currently active.

    Args:
        cfg: Runtime configuration.

    Returns:
        Number of removed JDK installations.
    """
    active_target = get_active_target(cfg.jdk_symlink)
    removed = 0
    if cfg.cache_dir.is_dir():
        for jdk_entry in cfg.cache_dir.glob("jdk-*"):
            if jdk_entry.is_dir():
                java_home = find_java_home_in_jdk_dir(jdk_entry)
                is_active = (
                    active_target
                    and java_home
                    and (
                        active_target == java_home or active_target.resolve() == java_home.resolve()
                    )
                )
                if not is_active:
                    if cfg.dry_run:
                        console.print(
                            f"  [yellow][dry-run] Would remove {format_path_for_display(jdk_entry)}[/yellow]"
                        )
                    else:
                        console.print(f"  Removing {format_path_for_display(jdk_entry)}")
                        shutil.rmtree(jdk_entry, ignore_errors=True)
                    removed += 1
    return removed


def render_which(cfg: Config) -> None:
    """Display active JAVA_HOME, binary paths, and PATH diagnostics.

    Args:
        cfg: Runtime configuration.
    """
    active_target = get_active_target(cfg.jdk_symlink)
    current_path = os.environ.get("PATH", "").split(os.pathsep)
    in_path = str(cfg.bin_dir) in current_path

    console.print("[bold]JDK Locations:[/bold]")
    console.print(f"  Active JAVA_HOME: {format_path_for_display(active_target)}")
    console.print(f"  Symlink:          {format_path_for_display(cfg.jdk_symlink)}")
    console.print(f"  Java Binary:      {format_path_for_display(cfg.java_launcher)}")
    console.print(f"  Javac Binary:     {format_path_for_display(cfg.javac_launcher)}")
    if in_path:
        console.print("  PATH Status:      [green]Launcher directory is in PATH[/green]")
    else:
        console.print(
            f"  PATH Status:      [yellow]Launcher directory is NOT in PATH ({format_path_for_display(cfg.bin_dir)})[/yellow]"
        )


# Typer Application
app = typer.Typer(
    name="install-jdk",
    help="Manages Java Development Kit (JDK) versions, cache storage, and executable shims.",
    no_args_is_help=True,
    add_completion=False,
)

# Common CLI Option Type Aliases
OptVerbose = Annotated[
    bool,
    typer.Option("-v", "--verbose", help="Enable verbose output and diagnostics"),
]
OptDryRun = Annotated[
    bool,
    typer.Option("-n", "--dry-run", help="Show what actions would be taken without making changes"),
]
OptForce = Annotated[
    bool,
    typer.Option(
        "-f", "--force", help="Force re-download / overwrite even if version exists in cache"
    ),
]
OptYes = Annotated[
    bool,
    typer.Option("-y", "--yes", help="Automatic yes to prompts; assume yes to all questions"),
]
OptDir = Annotated[
    Path | None,
    typer.Option("--dir", help="Install directory for active symlink"),
]
OptCacheDir = Annotated[
    Path | None,
    typer.Option("--cache-dir", help="Cache directory for versioned JDKs"),
]
OptBinDir = Annotated[
    Path | None,
    typer.Option("--bin-dir", help="Launcher binary directory"),
]


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
    """Retrieve runtime Config from context and apply any local CLI overrides.

    Args:
        ctx: Optional Typer Context.
        verbose: Verbose flag.
        dry_run: Dry-run flag.
        force: Force flag.
        yes: Automatic yes flag.
        dir_path: Install directory override.
        cache_dir: Cache directory override.
        bin_dir: Binary directory override.

    Returns:
        Config instance with all active settings applied.
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
    return cfg


@app.callback()
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
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Global configuration handler for CLI options."""
    if version:
        root = find_project_root()
        ver = get_project_version(root)
        console.print(f"install-jdk.py (cs1302-code-visualizer {ver})")
        raise typer.Exit(0)

    cfg = create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        yes=yes,
    )
    if ctx:
        ctx.obj = cfg


@app.command("install", help="Install specified (or latest LTS) JDK into cache and link it.")
def cmd_install(
    version_tag: Annotated[
        str | None,
        typer.Argument(
            help="Specific JDK major version or release tag (e.g. 21, 25, default: latest LTS)",
        ),
    ] = None,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Install specified (or latest LTS) JDK into cache and link it."""
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
    target = version_tag or "latest"
    apply_version_link(target, cfg, is_explicit_use=bool(version_tag))


@app.command("update", help="Check Adoptium for the latest JDK release and update active link.")
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
    """Check Adoptium for the latest JDK release and update active link."""
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
    latest_lts = get_latest_adoptium_lts()
    cfg.force = True
    apply_version_link(latest_lts, cfg, is_explicit_use=True)


@app.command("use", help="Switch active version to VERSION (downloads to cache if missing).")
@app.command("set", hidden=True)
def cmd_use(
    version_tag: Annotated[
        str,
        typer.Argument(
            help="Release version to activate (e.g. 21, 25, or latest)",
        ),
    ],
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Switch active version to VERSION (downloads to cache if missing)."""
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
    apply_version_link(version_tag, cfg, is_explicit_use=True)


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
    render_versions_table(cfg)


@app.command("status", help="Display current version, latest release, and symlink paths.")
@app.command("check", hidden=True)
@app.command("info", hidden=True)
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
    render_status(cfg)


@app.command("clean", help="Remove cached JDK installations that are not currently active.")
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
    """Remove cached JDK installations that are not currently active."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        yes=yes,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
    )
    active_target = get_active_target(cfg.jdk_symlink)
    unused_entries: list[Path] = []
    if cfg.cache_dir.is_dir():
        for jdk_entry in cfg.cache_dir.glob("jdk-*"):
            if jdk_entry.is_dir():
                java_home = find_java_home_in_jdk_dir(jdk_entry)
                is_active = (
                    active_target
                    and java_home
                    and (
                        active_target == java_home or active_target.resolve() == java_home.resolve()
                    )
                )
                if not is_active:
                    unused_entries.append(jdk_entry)

    if not unused_entries:
        console.print("No unused cached JDK installations found.")
        return

    if (
        not cfg.yes
        and not cfg.dry_run
        and not typer.confirm(
            f"Remove {len(unused_entries)} unused cached JDK installation(s)?", default=True
        )
    ):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    removed = clean_cache(cfg)
    if cfg.dry_run:
        console.print(
            f"[yellow][dry-run][/yellow] Would remove {removed} unused JDK installation(s)."
        )
    else:
        console.print(f"Done. Removed {removed} unused JDK installation(s).")


@app.command("which", help="Display active JAVA_HOME path and launcher binary locations.")
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display active JAVA_HOME path and launcher binary locations."""
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
    help="Run a command with target JDK JAVA_HOME exported and bin directory prepended to PATH.",
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
            help="Select a specific JDK version for this execution",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable verbose diagnostics")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what actions would be taken")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Force re-download")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Automatic yes")] = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
) -> None:
    """Run a command with target JDK JAVA_HOME exported and bin prepended to PATH."""
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
    # Reconstruct raw args from sys.argv after 'exec'/'run' to avoid flag collision (e.g. -version)
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
            f"[red]error:[/red] 'exec' requires a command to execute (e.g. 'install-jdk.py exec java -version')"
        )
        raise typer.Exit(1)

    if use_val:
        _, java_home, _ = download_and_extract_jdk(use_val, cfg)
    else:
        active_target = get_active_target(cfg.jdk_symlink)
        if not active_target:
            _, java_home, _ = download_and_extract_jdk("latest", cfg)
            apply_version_link("latest", cfg)
        else:
            java_home = active_target

    target_bin = java_home / "bin"
    cfg.log(
        f"Executing command with PATH={target_bin}:$PATH JAVA_HOME={java_home} -> {' '.join(cmd_args)}"
    )

    if cfg.dry_run:
        console.print(
            f'[yellow][dry-run] JAVA_HOME="{java_home}" PATH="{target_bin}:$PATH" exec {" ".join(cmd_args)}[/yellow]'
        )
        return

    new_env = os.environ.copy()
    new_env["JAVA_HOME"] = str(java_home)
    new_env["PATH"] = f"{target_bin}{os.pathsep}{new_env.get('PATH', '')}"

    try:
        res = subprocess.run(cmd_args, env=new_env, check=False)
        sys.exit(res.returncode)
    except Exception as exc:
        err_console.print(f"[red]error:[/red] Failed to execute command: {exc}")
        sys.exit(1)


@app.command(
    "help",
    help="Display help information for JDK installer or a specific command.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_help(
    ctx: typer.Context,
) -> None:
    """Display CLI help or help for a specific subcommand."""
    root_ctx = ctx.find_root()
    if not ctx.args:
        click.echo(root_ctx.get_help())
        raise typer.Exit(0)

    curr_cmd = root_ctx.command
    curr_ctx = root_ctx
    for arg in ctx.args:
        if hasattr(curr_cmd, "get_command"):
            sub_cmd = curr_cmd.get_command(curr_ctx, arg)
            if sub_cmd is not None:
                curr_cmd = sub_cmd
                curr_ctx = click.Context(curr_cmd, parent=curr_ctx, info_name=arg)
                continue
        err_console.print(f"[red]error:[/red] Unknown command '{arg}'.")
        raise typer.Exit(2)

    click.echo(curr_ctx.get_help())
    raise typer.Exit(0)


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
    short: Annotated[
        bool,
        typer.Option(
            "-s",
            "--short",
            help="Print only the project version string",
        ),
    ] = False,
) -> None:
    """Display script and project version."""
    root = find_project_root()
    ver = get_project_version(root)
    if short:
        console.print(ver)
    else:
        console.print(f"install-jdk.py (cs1302-code-visualizer {ver})")


@self_app.command("path", help="Display the path of this script.")
@self_app.command("which", hidden=True)
def cmd_self_path() -> None:
    """Display the path of this script."""
    console.print(format_path_for_display(Path(__file__).resolve()))


def main() -> None:
    """Main CLI entry point for the script."""
    try:
        app()
    except Exception as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    main()
