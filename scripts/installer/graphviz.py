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
"""Graphviz standalone version and installation manager.

Downloads prebuilt Graphviz binary packages from GitLab Releases API into a cache
directory and manages active executables via atomic symlinks and shims.
"""

from __future__ import annotations

import os
import platform
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
    resolve_default_man_dir,
    resolve_shims_bin_dir,
    resolve_shims_man_dir,
)
from scripts.installer.common import (
    download_file as common_download_file,
)

console = Console()
err_console = Console(stderr=True)

OptManDir = Annotated[
    Path | None,
    typer.Option(
        "--man-dir",
        help="Man pages directory override (default: .venv/share/man or scripts/installer/shims/share/man).",
        show_default=False,
        metavar="<path>",
    ),
]

GITLAB_PROJECT_API = "https://gitlab.com/api/v4/projects/graphviz%2Fgraphviz"
GITLAB_WEB_RELEASES = "https://gitlab.com/graphviz/graphviz/-/releases"

GRAPHVIZ_KNOWN_BINARIES: frozenset[str] = frozenset({
    "acyclic",
    "bcomps",
    "ccomps",
    "circo",
    "cluster",
    "dijkstra",
    "dot",
    "dot2gxl",
    "dot_builtins",
    "dot_sandbox",
    "edgepaint",
    "fdp",
    "gc",
    "gml2gv",
    "graphml2gv",
    "gv2gml",
    "gv2gxl",
    "gvcolor",
    "gvedit",
    "gvgen",
    "gvmap",
    "gvmap.sh",
    "gvpack",
    "gvpr",
    "gxl2dot",
    "gxl2gv",
    "mingle",
    "mm2gv",
    "neato",
    "nop",
    "osage",
    "patchwork",
    "prune",
    "sccmap",
    "sfdp",
    "tred",
    "twopi",
    "unflatten",
    "vimdot",
})


def get_min_graphviz_version(root_dir: Path) -> str | None:
    """Read minimum Graphviz version from pyproject.toml.

    Args:
        root_dir: Root directory of the project.

    Returns:
        Configured minimum version string if present, else None.
    """
    return get_min_system_dependency_version(root_dir, "graphviz")


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
        """Path to the primary 'dot' launcher executable."""
        return self.bin_dir / "dot"

    def log(self, message: str) -> None:
        """Print verbose log if enabled.

        Args:
            message: Message to log to standard error.
        """
        if self.verbose:
            err_console.print(f"[dim][install_graphviz.py][/dim] {message}")


def resolve_default_paths(root_dir: Path | None = None) -> tuple[Path, Path, Path, Path]:
    """Resolve default directories based on the project root directory.

    Args:
        root_dir: Optional root directory of the project.

    Returns:
        A tuple of (default_install_dir, default_cache_dir, default_bin_dir, default_man_dir).
    """
    root = root_dir or find_project_root()
    default_install_dir = root / "scripts" / "cache" / "graphviz"
    default_cache_dir = root / "scripts" / "cache" / "graphviz"
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
    env_install = os.environ.get("GRAPHVIZ_INSTALL_DIR") or os.environ.get("CS1302_INSTALL_DIR")
    env_cache = os.environ.get("GRAPHVIZ_CACHE_DIR") or os.environ.get("CS1302_CACHE_DIR")
    env_bin = os.environ.get("GRAPHVIZ_BIN_DIR") or os.environ.get("CS1302_BIN_DIR")
    env_man = os.environ.get("GRAPHVIZ_MAN_DIR") or os.environ.get("CS1302_MAN_DIR")

    final_install = dir_path or (Path(env_install) if env_install else def_install)
    final_cache = cache_dir or (Path(env_cache) if env_cache else def_cache)
    final_bin = bin_dir or (Path(env_bin) if env_bin else def_bin)
    final_man = man_dir or (Path(env_man) if env_man else def_man)

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
        man_dir: Man dir override.

    Returns:
        Config instance with combined flags.
    """
    if ctx is not None and getattr(ctx, "obj", None) is not None and isinstance(ctx.obj, Config):
        cfg = ctx.obj
        return Config(
            install_dir=dir_path or cfg.install_dir,
            cache_dir=cache_dir or cfg.cache_dir,
            bin_dir=bin_dir or cfg.bin_dir,
            man_dir=man_dir or cfg.man_dir,
            verbose=verbose or cfg.verbose,
            dry_run=dry_run or cfg.dry_run,
            force=force or cfg.force,
            yes=yes or cfg.yes,
        )
    return create_default_config(
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
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
    """Determine the installed version from active target path.

    Args:
        target: Target directory path of the active installation symlink.

    Returns:
        Version tag string or None if uninstalled.
    """
    active = get_active_target(target) if target else None
    if not active:
        return None
    name = active.name
    clean_name = clean_version_tag(name)
    if any(c.isdigit() for c in clean_name):
        return clean_name

    dot_bin = active / "bin" / "dot"
    if not dot_bin.exists() and (active / "dot").exists():
        dot_bin = active / "dot"

    if dot_bin.exists():
        try:
            import re

            res = subprocess.run(
                [str(dot_bin), "-V"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
            output = res.stderr or res.stdout
            m = re.search(r"version\s+([0-9.]+)", output, re.IGNORECASE)
            if m:
                return m.group(1)
        except (OSError, subprocess.TimeoutExpired):
            pass

    return None


def get_gitlab_releases(cfg: Config | None = None) -> list[dict]:
    """Fetch releases list from GitLab REST API.

    Args:
        cfg: Optional runtime configuration.

    Returns:
        List of release metadata dictionaries from GitLab.
    """
    url = f"{GITLAB_PROJECT_API}/releases"
    if cfg:
        cfg.log(f"Fetching releases from {url}")
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
        if cfg:
            cfg.log(f"GitLab API returned status code {resp.status_code}")
    except (requests.RequestException, ValueError) as e:
        if cfg:
            cfg.log(f"GitLab API error: {e}")
    return []


def get_latest_gitlab_version() -> str | None:
    """Fetch the tag of the latest Graphviz release from GitLab.

    Returns:
        Latest release tag string (e.g. '16.0.0'), or None on failure.
    """
    url = f"{GITLAB_PROJECT_API}/releases/permalink/latest"
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "tag_name" in data:
                return clean_version_tag(str(data["tag_name"]))
    except (requests.RequestException, ValueError):
        pass

    try:
        resp = requests.get(
            f"{GITLAB_PROJECT_API}/releases?per_page=1",
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return clean_version_tag(str(data[0].get("tag_name", "")))
    except (requests.RequestException, ValueError):
        pass
    return None


def resolve_target_tag(tag: str, cfg: Config) -> tuple[str, str]:
    """Resolve 'latest' or requested tag to an exact version tag and clean string.

    Args:
        tag: Requested version tag or 'latest'.
        cfg: Runtime configuration.

    Returns:
        Tuple of (clean_version_string, raw_tag_name).
    """
    if tag.lower() == "latest":
        latest = get_latest_gitlab_version()
        if latest:
            return latest, latest
        releases = get_gitlab_releases(cfg)
        if releases:
            first_tag = str(releases[0].get("tag_name", ""))
            return clean_version_tag(first_tag), first_tag
        return "16.0.0", "16.0.0"
    return clean_version_tag(tag), tag


def find_matching_asset_url(release_data: dict, cfg: Config) -> tuple[str | None, str | None]:
    """Find prebuilt binary asset URL matching the current OS and architecture.

    Args:
        release_data: Release dictionary from GitLab API.
        cfg: Runtime configuration.

    Returns:
        Tuple of (download_url, filename) or (None, None) if not found.
    """
    system = platform.system()
    assets = release_data.get("assets", {})
    links = assets.get("links", [])

    candidates: list[tuple[str, str]] = []
    for link in links:
        if isinstance(link, dict):
            name = str(link.get("name", ""))
            url = str(link.get("direct_asset_url") or link.get("url") or "")
            if system == "Darwin":
                if ("darwin" in name.lower() and name.endswith(".zip")) or (
                    name.endswith(".pkg") and "arm64" in name and "arm64" in platform.machine()
                ):
                    candidates.append((url, name))
            elif system == "Windows":
                if ("win64" in name.lower() or "win32" in name.lower()) and name.endswith(".zip"):
                    candidates.append((url, name))
            else:  # Linux / Unix
                if name.endswith(("-debs.tar.xz", "-rpms.tar.xz", ".tar.xz", ".tar.gz")):
                    candidates.append((url, name))

    if candidates:
        cfg.log(f"Selected candidate asset: {candidates[0][1]}")
        return candidates[0]

    for link in links:
        if isinstance(link, dict):
            name = str(link.get("name", ""))
            url = str(link.get("direct_asset_url") or link.get("url") or "")
            if name.endswith((".tar.xz", ".tar.gz", ".zip")) and not name.endswith(".sha256"):
                cfg.log(f"Fallback asset selected: {name}")
                return url, name

    return None, None


def download_file(url: str, target_file: Path, cfg: Config) -> bool:
    """Download a remote file to a local path.

    Args:
        url: Remote URL to download.
        target_file: Local destination Path.
        cfg: Runtime configuration.

    Returns:
        True if download succeeded, else False.
    """
    return common_download_file(
        url=url,
        dest_path=target_file,
        description=f"Downloading {target_file.name}",
        dry_run=cfg.dry_run,
        verbose=cfg.verbose,
    )


def unpack_archive(archive_path: Path, target_dir: Path, cfg: Config) -> None:
    """Unpack a zip or tar archive into target directory, flattening root folder.

    Args:
        archive_path: Path to archive file (.zip, .tar.gz, .tar.xz).
        target_dir: Destination directory.
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
            and extracted_items[0].name not in ("bin", "lib", "share", "include")
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

        bin_dir = target_dir / "bin"
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
    """Download and unpack a Graphviz release for the current platform.

    Args:
        tag: Version string or 'latest'.
        cfg: Runtime configuration.

    Returns:
        Path to unpacked version directory in cache.
    """
    clean_tag, _ = resolve_target_tag(tag, cfg)
    version_dir = cfg.cache_dir / clean_tag

    if not cfg.force and version_dir.exists():
        cfg.log(f"Using cached version directory: {version_dir}")
        return version_dir

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would download and unpack Graphviz v{clean_tag} to {format_path_for_display(version_dir)}[/yellow]"
        )
        return version_dir

    releases = get_gitlab_releases(cfg)
    target_rel = next(
        (r for r in releases if clean_version_tag(str(r.get("tag_name", ""))) == clean_tag),
        None,
    )

    asset_url: str | None = None
    asset_name: str | None = None
    if target_rel:
        asset_url, asset_name = find_matching_asset_url(target_rel, cfg)

    if not asset_url:
        system = platform.system()
        if system == "Darwin":
            asset_name = f"Graphviz-{clean_tag}-Darwin.zip"
        elif system == "Windows":
            asset_name = f"windows_10_cmake_Release_Graphviz-{clean_tag}-win64.zip"
        else:
            asset_name = f"graphviz-{clean_tag}.tar.gz"
        asset_url = (
            f"{GITLAB_PROJECT_API}/packages/generic/graphviz-releases/{clean_tag}/{asset_name}"
        )

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    archive_file = cfg.cache_dir / f"graphviz-{clean_tag}-{asset_name}"

    if not archive_file.is_file() or cfg.force:
        success = download_file(asset_url, archive_file, cfg)
        if not success:
            err_console.print(
                f"[red]error:[/red] Failed to download Graphviz asset from {asset_url}"
            )
            raise typer.Exit(1)

    with err_console.status(
        f"[bold cyan]Unpacking Graphviz v{clean_tag}...[/bold cyan]",
        spinner="dots",
    ):
        if version_dir.exists():
            shutil.rmtree(version_dir)
        unpack_archive(archive_file, version_dir, cfg)

    return version_dir


def create_shims_for_version(target_dir: Path, cfg: Config) -> list[str]:
    """Generate wrapper shims in bin_dir for all Graphviz executables.

    Args:
        target_dir: Active installation directory containing bin/.
        cfg: Runtime configuration.

    Returns:
        List of generated shim executable names.
    """
    bin_sub = target_dir / "bin"
    search_dir = bin_sub if bin_sub.is_dir() else target_dir

    shims_created: list[str] = []
    if cfg.dry_run:
        return ["dot", "neato", "circo", "fdp", "sfdp", "twopi"]

    cfg.bin_dir.mkdir(parents=True, exist_ok=True)

    for item in search_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            try:
                item.chmod(item.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except OSError:  # pragma: no cover
                pass
            name = item.name
            shim_path = cfg.bin_dir / name
            content = f"""#!/usr/bin/env bash
#
# Graphviz launcher wrapper generated by install_graphviz.py
set -euo pipefail

GRAPHVIZ_ROOT="{cfg.current_link}"
BINARY_NAME="{name}"
BINARY_PATH="${{GRAPHVIZ_ROOT}}/bin/${{BINARY_NAME}}"

if [[ ! -x "${{BINARY_PATH}}" ]]; then
    if [[ -x "${{GRAPHVIZ_ROOT}}/${{BINARY_NAME}}" ]]; then
        BINARY_PATH="${{GRAPHVIZ_ROOT}}/${{BINARY_NAME}}"
    else
        printf "error: Graphviz binary '%s' not found at %s. Please run install_graphviz.py to reinstall.\\n" "${{BINARY_NAME}}" "${{BINARY_PATH}}" >&2
        exit 1
    fi
fi

if [[ -d "${{GRAPHVIZ_ROOT}}/lib" ]]; then
    export DYLD_LIBRARY_PATH="${{GRAPHVIZ_ROOT}}/lib:${{DYLD_LIBRARY_PATH:-}}"
    export LD_LIBRARY_PATH="${{GRAPHVIZ_ROOT}}/lib:${{LD_LIBRARY_PATH:-}}"
fi

exec "${{BINARY_PATH}}" "$@"
"""
            shim_path.write_text(content, encoding="utf-8")
            shim_path.chmod(0o755)
            shims_created.append(name)

    return shims_created


def find_source_man_dir(version_dir: Path) -> Path | None:
    """Find man directory inside an extracted Graphviz release.

    Args:
        version_dir: Extracted Graphviz release root directory.

    Returns:
        Path to share/man or man directory if found, else None.
    """
    for candidate in (version_dir / "share" / "man", version_dir / "man"):
        if candidate.is_dir():
            return candidate
    return None


def create_man_page_symlinks(
    version_dir: Path,
    cfg: Config,
) -> list[Path]:
    """Create symlinks in cfg.man_dir for all man pages in version_dir.

    Args:
        version_dir: Path to the active Graphviz installation directory.
        cfg: Runtime configuration.

    Returns:
        List of created symlink paths.
    """
    src_man = find_source_man_dir(version_dir)
    if not src_man or not src_man.is_dir():
        return []

    created_links: list[Path] = []
    for section_dir in sorted(src_man.iterdir()):
        if section_dir.is_dir() and not section_dir.name.startswith("."):
            dest_section_dir = cfg.man_dir / section_dir.name
            if not cfg.dry_run:
                dest_section_dir.mkdir(parents=True, exist_ok=True)
            for man_file in sorted(section_dir.iterdir()):
                if man_file.is_file() and not man_file.name.startswith("."):
                    dest_link = dest_section_dir / man_file.name
                    if not cfg.dry_run:
                        if dest_link.is_symlink() or dest_link.exists():
                            dest_link.unlink()
                        try:
                            rel_target = os.path.relpath(
                                man_file.resolve(), dest_section_dir.resolve()
                            )
                            dest_link.symlink_to(rel_target)
                        except (ValueError, OSError):  # pragma: no cover
                            dest_link.symlink_to(man_file.resolve())
                    created_links.append(dest_link)

    cfg.log(f"Linked {len(created_links)} man page(s) in {cfg.man_dir}")
    return created_links


def remove_man_page_symlinks(
    cfg: Config,
) -> list[Path]:
    """Remove Graphviz man page symlinks from cfg.man_dir.

    Args:
        cfg: Runtime configuration.

    Returns:
        List of removed man page symlinks.
    """
    removed: list[Path] = []
    if not cfg.man_dir.is_dir():
        return removed

    for section_dir in sorted(cfg.man_dir.iterdir()):
        if section_dir.is_dir() and not section_dir.name.startswith("."):
            for item in sorted(section_dir.iterdir()):
                if item.is_symlink() or item.is_file():
                    is_gv_man = False
                    if item.is_symlink():
                        try:
                            target = item.resolve()
                            if (
                                "graphviz" in str(target).lower()
                                or str(target).startswith(str(cfg.cache_dir.resolve()))
                                or str(target).startswith(str(cfg.install_dir.resolve()))
                                or not item.exists()
                            ):
                                is_gv_man = True
                        except OSError:  # pragma: no cover
                            is_gv_man = True
                    base_name = item.name.split(".")[0]
                    if (
                        base_name in GRAPHVIZ_KNOWN_BINARIES
                        or item.name.startswith("gv")
                        or item.name.startswith("dot")
                    ):
                        is_gv_man = True
                    if is_gv_man:
                        removed.append(item)
                        if not cfg.dry_run:
                            try:
                                item.unlink()
                            except OSError:  # pragma: no cover
                                pass
            if not cfg.dry_run and section_dir.is_dir():
                try:
                    if not any(section_dir.iterdir()):
                        section_dir.rmdir()
                except OSError:  # pragma: no cover
                    pass

    return removed


def apply_version_link(
    tag: str,
    cfg: Config,
    is_explicit_use: bool = False,
) -> Path:
    """Activate a version by updating current symlink, shims, and man pages.

    Args:
        tag: Version string to link.
        cfg: Runtime configuration.
        is_explicit_use: Whether invoked by 'use' command.

    Returns:
        Path to the active version directory.
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
    man_links = create_man_page_symlinks(version_dir, cfg)

    console.print()
    console.print("[bold green]Graphviz successfully configured![/bold green]")
    console.print(f"  Installed Path: {format_path_for_display(version_dir)}")
    console.print(
        f"  Active Link:    {format_path_for_display(cfg.current_link)} -> {format_path_for_display(version_dir)}"
    )
    console.print(
        f"  Created Shims:  {len(shims)} binaries in {format_path_for_display(cfg.bin_dir)}"
    )
    if man_links:
        console.print(
            f"  Created Man:    {len(man_links)} man pages in {format_path_for_display(cfg.man_dir)}"
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
            "To use 'dot' and Graphviz tools directly from your terminal, add it to your PATH:"
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


def uninstall_graphviz(
    cfg: Config,
    purge: bool = False,
) -> tuple[list[Path], Path | None, list[Path], list[Path]]:
    """Uninstall Graphviz by removing launcher shims, man pages, active link, and optionally caches.

    Args:
        cfg: Runtime configuration.
        purge: Whether to remove cached versions and archives as well.

    Returns:
        A tuple of (removed_shims, removed_symlink, removed_cache_items, removed_man_pages).
    """
    removed_shims: list[Path] = []
    removed_link: Path | None = None
    removed_cache: list[Path] = []
    removed_man: list[Path] = remove_man_page_symlinks(cfg)

    if cfg.bin_dir.is_dir():
        for item in cfg.bin_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                is_shim = False
                if item.name in GRAPHVIZ_KNOWN_BINARIES:
                    is_shim = True
                else:
                    try:
                        header = item.read_text(encoding="utf-8", errors="ignore")[:200]
                        if "install_graphviz.py" in header or "GRAPHVIZ_ROOT" in header:
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

    return removed_shims, removed_link, removed_cache, removed_man


def render_which(cfg: Config) -> None:
    """Print the location of the active binary and wrapper shim.

    Args:
        cfg: Runtime configuration.
    """
    active_target = get_active_target(cfg.current_link)
    dot_bin = (active_target / "bin" / "dot") if active_target else None

    console.print("[bold]Graphviz Locations:[/bold]")
    if dot_bin and dot_bin.exists():
        console.print(f"  Active Binary: {format_path_for_display(dot_bin)}")
    else:
        console.print("  Active Binary: [red]none (not installed or unlinked)[/red]")

    if active_target:
        console.print(f"  Symlink:       {format_path_for_display(active_target)}")
    else:
        console.print("  Symlink:       [red]none[/red]")

    if cfg.primary_executable.exists():
        console.print(f"  Launcher:      {format_path_for_display(cfg.primary_executable)}")
    else:
        console.print("  Launcher:      [red]none (shim missing)[/red]")

    console.print(f"  Man Pages:     {format_path_for_display(cfg.man_dir)}")

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
        Tuple of (temp_bin_dir, path_to_transient_dot).
    """
    tmp_bin = Path(tempfile.mkdtemp(prefix="gv_exec_"))
    dot_shim = tmp_bin / "dot"
    bin_dir = (
        target_version_dir / "bin" if (target_version_dir / "bin").is_dir() else target_version_dir
    )

    for item in bin_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            s_path = tmp_bin / item.name
            content = f"""#!/usr/bin/env bash
set -euo pipefail
BINARY_PATH="{item.resolve()}"
if [[ -d "{target_version_dir / "lib"}" ]]; then
    export DYLD_LIBRARY_PATH="{target_version_dir / "lib"}:${{DYLD_LIBRARY_PATH:-}}"
    export LD_LIBRARY_PATH="{target_version_dir / "lib"}:${{LD_LIBRARY_PATH:-}}"
fi
exec "${{BINARY_PATH}}" "$@"
"""
            s_path.write_text(content, encoding="utf-8")
            s_path.chmod(0o755)

    return tmp_bin, dot_shim


def run_exec_command(
    command_args: list[str],
    bin_dir_to_use: Path,
    temp_dir_to_cleanup: Path | None,
    cfg: Config,
) -> None:
    """Execute a shell command with Graphviz binary and man paths prepended.

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
    if cfg.man_dir.is_dir():
        env["MANPATH"] = f"{cfg.man_dir.resolve()}{os.pathsep}{env.get('MANPATH', '')}"

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
    name=Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-graphviz",
    help="Manages Graphviz standalone binaries, cache storage, and executable shims.",
    no_args_is_help=True,
    add_completion=False,
)


def cli_version_callback(value: bool) -> None:
    """Print version string and exit."""
    if value:
        root = find_project_root()
        ver = get_project_version(root)
        console.print(f"install_graphviz.py (cs1302-book {ver})")
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
    man_dir: OptManDir = None,
) -> None:
    """Configure runtime options in Typer context."""
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
    ctx.obj = cfg


@app.command("install", help="Install specified (or latest) release into cache and link shims.")
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
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Install specified (or latest) release into cache and link shims."""
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
    clean_tag, _ = resolve_target_tag(tag, cfg)
    version_dir = cfg.cache_dir / clean_tag

    if not cfg.yes and not cfg.dry_run:
        prompt = f"Install and activate Graphviz v{clean_tag}?"
        if not typer.confirm(prompt, default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    if version_dir.exists() and not cfg.force:
        console.print(f"Using existing cached version: {format_path_for_display(version_dir)}")

    apply_version_link(tag, cfg, is_explicit_use=False)


@app.command("update", help="Check GitLab and update to the latest release.")
def cmd_update(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    force: OptForce = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Check GitLab and update to the latest release."""
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
    current_ver = get_installed_version(cfg.current_link)
    latest_ver = get_latest_gitlab_version()

    if not latest_ver:
        err_console.print("[red]error:[/red] Unable to retrieve latest release from GitLab.")
        raise typer.Exit(1)

    if current_ver and is_version_ge(current_ver, latest_ver) and not cfg.force:
        console.print(f"Graphviz is already up to date ({current_ver}).")
        return

    if not cfg.yes and not cfg.dry_run:
        prompt = (
            f"Update Graphviz from {current_ver or 'none'} to {latest_ver}?"
            if current_ver
            else f"Install latest Graphviz release (v{latest_ver})?"
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
    man_dir: OptManDir = None,
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
        man_dir=man_dir,
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
    man_dir: OptManDir = None,
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
        man_dir=man_dir,
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
        console.print("No Graphviz versions currently installed in cache.")
        return

    table = Table(title="Installed Graphviz Versions", box=None)
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
    man_dir: OptManDir = None,
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
        man_dir=man_dir,
    )
    installed_ver = get_installed_version(cfg.current_link)
    with err_console.status(
        "[bold cyan]Checking latest GitLab release...[/bold cyan]", spinner="dots"
    ):
        latest_ver = get_latest_gitlab_version()

    root = find_project_root()
    min_ver = get_min_graphviz_version(root)

    console.print("[bold]Graphviz Installation Status:[/bold]")
    console.print(f"  Active version:       {installed_ver or 'none (not installed)'}")
    console.print(f"  Latest GitLab tag:    {latest_ver or 'unknown'}")
    if min_ver:
        console.print(f"  Project min version:  {min_ver}")
    console.print(f"  Man directory:        {format_path_for_display(cfg.man_dir)}")

    console.print()
    if not installed_ver:
        console.print(
            "[yellow]Status: Graphviz is not installed. Run 'install_graphviz.py install' to install.[/yellow]"
        )
    elif latest_ver and is_version_ge(installed_ver, latest_ver):
        console.print("[green]Status: Graphviz is up to date.[/green]")
    elif latest_ver and not is_version_ge(installed_ver, latest_ver):
        console.print(
            f"[yellow]Status: Update available ({installed_ver} -> {latest_ver}). Run 'install_graphviz.py update' to upgrade.[/yellow]"
        )
    elif min_ver and not is_version_ge(installed_ver, min_ver):
        console.print(
            f"[red]Status: Installed version ({installed_ver}) does not satisfy project min requirement (>={min_ver}).[/red]"
        )


@app.command("clean", help="Remove cached versions that are not currently active.")
@app.command("prune", hidden=True)
def cmd_clean(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Remove cached versions that are not currently active."""
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
            f"[yellow]\\[dry-run] Scanning unused Graphviz cache in {format_path_for_display(cfg.cache_dir)}...[/yellow]"
        )
    else:
        console.print(
            f"Cleaning unused Graphviz cache in {format_path_for_display(cfg.cache_dir)}..."
        )

    removed = clean_cache(cfg)

    if cfg.dry_run:
        console.print(f"[yellow]\\[dry-run] Would remove {removed} unused version(s).[/yellow]")
    else:
        console.print(f"Done. Removed {removed} unused version(s).")


@app.command("uninstall", help="Uninstall Graphviz shims and active installation.")
def cmd_uninstall(
    purge: OptPurge = False,
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    yes: OptYes = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Uninstall Graphviz by removing launcher shims, man pages, and active link."""
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
        "Uninstall Graphviz and remove all cached downloads?"
        if purge
        else "Uninstall Graphviz (remove launchers, man pages, and active symlink)?"
    )
    if not cfg.yes and not cfg.dry_run and not typer.confirm(prompt_msg, default=True):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    if cfg.dry_run:
        console.print("[yellow]\\[dry-run] Simulating Graphviz uninstallation...[/yellow]")
    else:
        console.print("Uninstalling Graphviz...")

    removed_shims, removed_link, removed_cache, removed_man = uninstall_graphviz(cfg, purge=purge)

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would remove {len(removed_shims)} launcher shim(s)[/yellow]"
        )
        if removed_man:
            console.print(
                f"[yellow]\\[dry-run] Would remove {len(removed_man)} man page symlink(s)[/yellow]"
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
        if removed_man:
            console.print(f"Removed {len(removed_man)} man page symlink(s).")
        if removed_link:
            console.print(f"Removed active link: {format_path_for_display(removed_link)}")
        if purge:
            console.print(f"Removed {len(removed_cache)} cached item(s).")
        console.print("[bold green]Graphviz successfully uninstalled.[/bold green]")


@app.command("which", help="Display active Graphviz binary path and launcher shims location.")
def cmd_which(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Display active Graphviz binary path and launcher shims location."""
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


@app.command(
    "exec",
    help="Run a command with Graphviz bin directory prepended to PATH.",
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
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Run a command with Graphviz bin directory prepended to PATH."""
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=bin_dir,
        man_dir=man_dir,
    )
    extra_args = list(ctx.args) if ctx and ctx.args else []
    if not extra_args:
        err_console.print("[red]error:[/red] No command specified to execute.")
        raise typer.Exit(1)

    if use:
        clean_tag, _ = resolve_target_tag(use, cfg)
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
    help="Clear and regenerate Graphviz shims in scripts/installer/shims/bin (or custom bin-dir).",
)
def cmd_rehash(
    verbose: OptVerbose = False,
    dry_run: OptDryRun = False,
    dir_path: OptDir = None,
    cache_dir: OptCacheDir = None,
    bin_dir: OptBinDir = None,
    man_dir: OptManDir = None,
    ctx: typer.Context = None,  # type: ignore
) -> None:
    """Clear and rebuild Graphviz executable shims and man pages."""
    root = find_project_root()
    target_bin = bin_dir or resolve_shims_bin_dir(root)
    target_man = man_dir or resolve_shims_man_dir(root)
    cfg = get_config_from_context(
        ctx,
        verbose=verbose,
        dry_run=dry_run,
        dir_path=dir_path,
        cache_dir=cache_dir,
        bin_dir=target_bin,
        man_dir=target_man,
    )
    active_target = get_active_target(cfg.current_link)
    if not active_target:
        console.print(
            "[yellow]Graphviz is not currently installed or linked. Run 'install-graphviz install' first.[/yellow]"
        )
        return

    if cfg.dry_run:
        console.print(
            f"[yellow]\\[dry-run] Would clear and recreate Graphviz shims in {format_path_for_display(cfg.bin_dir)} and man pages in {format_path_for_display(cfg.man_dir)}[/yellow]"
        )
        return

    if cfg.bin_dir.is_dir():
        for item in cfg.bin_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                is_graphviz = False
                if item.name in GRAPHVIZ_KNOWN_BINARIES:
                    is_graphviz = True
                else:
                    try:
                        header = item.read_text(encoding="utf-8", errors="ignore")[:200]
                        if "install-graphviz" in header or "GRAPHVIZ_ROOT" in header:
                            is_graphviz = True
                    except OSError:  # pragma: no cover
                        pass
                if is_graphviz:
                    try:
                        item.unlink()
                    except OSError:  # pragma: no cover
                        pass

    remove_man_page_symlinks(cfg)

    shims = create_shims_for_version(active_target, cfg)
    man_links = create_man_page_symlinks(active_target, cfg)
    console.print(
        f"[bold green]Rehashed {len(shims)} Graphviz shim(s) in {format_path_for_display(cfg.bin_dir)} and {len(man_links)} man page(s) in {format_path_for_display(cfg.man_dir)}.[/bold green]"
    )


@app.command("help", help="Display help information for graphviz installer or a specific command.")
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
    """Display help information for graphviz installer or a specific command."""
    cli_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "install-graphviz"
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
        console.print(f"install_graphviz.py (cs1302-book {ver})")


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
