"""Unit tests for the UV standalone installer module."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import typer
from typer.testing import CliRunner

from scripts.installer import uv
from scripts.installer.uv import Config, app

runner = CliRunner()


def test_get_min_uv_version(tmp_path: Path) -> None:
    """Test reading minimum uv version from pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    _ = pyproject.write_text(
        '[tool.cs1302book.system-dependencies]\nsystem-dependencies = ["uv>=0.11.0"]\n',
        encoding="utf-8",
    )
    ver = uv.get_min_uv_version(tmp_path)
    assert ver == "0.11.0"


def test_config_properties_and_logging(tmp_path: Path) -> None:
    """Test Config property methods and verbose logging."""
    cfg = Config(
        install_dir=tmp_path / "install",
        cache_dir=tmp_path / "cache",
        bin_dir=tmp_path / "bin",
        man_dir=tmp_path / "man",
        verbose=True,
    )
    assert cfg.current_link == tmp_path / "install" / "current"
    assert cfg.primary_executable == tmp_path / "bin" / "uv"

    with patch.object(uv.err_console, "print") as mock_print:
        cfg.log("Test verbose message")
        mock_print.assert_called_once()

    cfg.verbose = False
    with patch.object(uv.err_console, "print") as mock_print_silent:
        cfg.log("Silent message")
        mock_print_silent.assert_not_called()


def test_resolve_default_paths(tmp_path: Path) -> None:
    """Test default directory path resolution."""
    install_d, cache_d, bin_d, man_d = uv.resolve_default_paths(tmp_path)
    assert install_d == tmp_path / "scripts" / "cache" / "uv"
    assert cache_d == tmp_path / "scripts" / "cache" / "uv"
    assert bin_d.name == "bin"
    assert man_d.name == "man"


def test_create_default_config_environment_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test environment variable overrides in create_default_config."""
    monkeypatch.setenv("UV_INSTALL_DIR", str(tmp_path / "custom_install"))
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "custom_cache"))
    monkeypatch.setenv("UV_BIN_DIR", str(tmp_path / "custom_bin"))
    monkeypatch.setenv("UV_MAN_DIR", str(tmp_path / "custom_man"))
    monkeypatch.setenv("VERBOSE", "1")

    cfg = uv.create_default_config()
    assert cfg.install_dir == tmp_path / "custom_install"
    assert cfg.cache_dir == tmp_path / "custom_cache"
    assert cfg.bin_dir == tmp_path / "custom_bin"
    assert cfg.man_dir == tmp_path / "custom_man"
    assert cfg.verbose is True


def test_detect_platform_archive() -> None:
    """Test target platform archive detection across OS and architectures."""
    with (
        patch("platform.system", return_value="Darwin"),
        patch("platform.machine", return_value="arm64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "aarch64-apple-darwin" in name
        assert fmt == "tar.gz"

    with (
        patch("platform.system", return_value="Darwin"),
        patch("platform.machine", return_value="x86_64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "x86_64-apple-darwin" in name
        assert fmt == "tar.gz"

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="aarch64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "aarch64-unknown-linux-gnu" in name

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="armv7l"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "armv7-unknown-linux-gnueabihf" in name

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="i686"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "i686-unknown-linux-gnu" in name

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="x86_64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "x86_64-unknown-linux-gnu" in name

    with (
        patch("platform.system", return_value="Windows"),
        patch("platform.machine", return_value="arm64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "aarch64-pc-windows-msvc.zip" in name
        assert fmt == "zip"

    with (
        patch("platform.system", return_value="Windows"),
        patch("platform.machine", return_value="AMD64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "x86_64-pc-windows-msvc.zip" in name
        assert fmt == "zip"

    with (
        patch("platform.system", return_value="FreeBSD"),
        patch("platform.machine", return_value="x86_64"),
    ):
        name, fmt = uv.detect_platform_archive("0.12.5")
        assert "x86_64-unknown-linux-musl" in name


def test_get_installed_version_nonexistent(tmp_path: Path) -> None:
    """Test version detection on nonexistent path returns None."""
    assert uv.get_installed_version(None) is None
    assert uv.get_installed_version(tmp_path / "does_not_exist") is None


def test_get_installed_version_with_executable(tmp_path: Path) -> None:
    """Test detecting installed version via executable execution."""
    bin_file = tmp_path / "uv"
    _ = bin_file.write_text("#!/bin/sh\n", encoding="utf-8")
    _ = bin_file.chmod(0o755)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[str(bin_file), "--version"],
            returncode=0,
            stdout="uv 0.12.5 (2026-08-01)",
            stderr="",
        )
        ver = uv.get_installed_version(bin_file)
        assert ver == "0.12.5"

    # Directory with bin/uv
    dir_path = tmp_path / "uv_dir"
    (dir_path / "bin").mkdir(parents=True)
    _ = (dir_path / "bin" / "uv").write_text("#!/bin/sh\n", encoding="utf-8")
    _ = (dir_path / "bin" / "uv").chmod(0o755)
    with patch("subprocess.run") as mock_run_dir:
        mock_run_dir.return_value = subprocess.CompletedProcess(
            args=[str(dir_path / "bin" / "uv"), "--version"],
            returncode=0,
            stdout="0.12.5",
            stderr="",
        )
        ver_dir = uv.get_installed_version(dir_path)
        assert ver_dir == "0.12.5"


def test_get_installed_version_fallbacks(tmp_path: Path) -> None:
    """Test directory name regex fallbacks when execution fails or no binary."""
    # Executable in dir fails execution, falls back to dir name
    dir_ver = tmp_path / "0.11.17"
    dir_ver.mkdir()
    _ = (dir_ver / "uv").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    _ = (dir_ver / "uv").chmod(0o755)
    with patch("subprocess.run", side_effect=OSError("Exec error")):
        assert uv.get_installed_version(dir_ver) == "0.11.17"

    # Executable fails and dirname has no digits
    no_num = tmp_path / "nodigits"
    no_num.mkdir()
    _ = (no_num / "uv").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    _ = (no_num / "uv").chmod(0o755)
    with patch("subprocess.run", side_effect=OSError("Exec error")):
        assert uv.get_installed_version(no_num) is None

    # No binary, but dir name matches
    empty_ver = tmp_path / "0.11.10"
    empty_ver.mkdir()
    assert uv.get_installed_version(empty_ver) == "0.11.10"

    # No binary, dir name does not match
    no_ver = tmp_path / "empty_dir"
    no_ver.mkdir()
    assert uv.get_installed_version(no_ver) is None


def test_get_latest_github_version_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fetching latest version tag from GitHub API."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"tag_name": "0.12.5"}
    with patch("requests.get", return_value=mock_resp):
        ver = uv.get_latest_github_version()
        assert ver == "0.12.5"

    # Fallback to list endpoint on 404
    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404
    mock_resp_list = MagicMock()
    mock_resp_list.status_code = 200
    mock_resp_list.json.return_value = [
        {"prerelease": True, "tag_name": "v0.13.0a1"},
        {"prerelease": False, "draft": False, "tag_name": "0.12.5"},
    ]
    with patch("requests.get", side_effect=[mock_resp_404, mock_resp_list]):
        ver_list = uv.get_latest_github_version()
        assert ver_list == "0.12.5"


def test_get_latest_github_version_fallback() -> None:
    """Test fallback when GitHub API request fails."""
    with patch("requests.get", side_effect=requests.RequestException("Network down")):
        ver = uv.get_latest_github_version()
        assert ver == uv.DEFAULT_FALLBACK_VERSION


def test_get_github_release_versions_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fetching release version list from GitHub."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"prerelease": False, "draft": False, "tag_name": "0.12.5"},
        {"prerelease": False, "draft": False, "tag_name": "0.12.4"},
    ]
    with patch("requests.get", return_value=mock_resp):
        versions = uv.get_github_release_versions()
        assert versions == ["0.12.5", "0.12.4"]


def test_get_github_release_versions_fallback() -> None:
    """Test fallback release version list when API fails."""
    with patch("requests.get", side_effect=requests.RequestException("Network down")):
        versions = uv.get_github_release_versions()
        assert uv.DEFAULT_FALLBACK_VERSION in versions


def test_resolve_target_tag(tmp_path: Path) -> None:
    """Test resolving target tag for 'latest' and explicit version strings."""
    cfg = Config(tmp_path, tmp_path, tmp_path, tmp_path)
    with patch.object(uv, "get_latest_github_version", return_value="0.12.5"):
        tag, url = uv.resolve_target_tag("latest", cfg)
        assert tag == "0.12.5"
        assert "0.12.5" in url

        tag_explicit, url_explicit = uv.resolve_target_tag("v0.11.17", cfg)
        assert tag_explicit == "0.11.17"
        assert "0.11.17" in url_explicit


def test_download_and_extract_uv(tmp_path: Path) -> None:
    """Test downloading and extracting UV release archive (tar.gz and zip)."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")

    # Already installed return
    target_d = cfg.cache_dir / "0.12.5"
    target_d.mkdir(parents=True)
    _ = (target_d / "uv").write_text("", encoding="utf-8")
    with patch.object(uv, "get_installed_version", return_value="0.12.5"):
        res = uv.download_and_extract_uv("0.12.5", cfg)
        assert res == target_d

    # Dry run
    cfg.dry_run = True
    res_dry = uv.download_and_extract_uv("0.12.5", cfg)
    assert res_dry == cfg.cache_dir / "0.12.5"
    cfg.dry_run = False

    # Download error
    cfg.force = True
    with (
        patch.object(uv, "common_download_file", return_value=False),
        pytest.raises(typer.Exit),
    ):
        _ = uv.download_and_extract_uv("0.12.5", cfg)

    # Extraction of tar.gz with nested directory
    inner_dir = tmp_path / "fake_extract" / "uv-aarch64-apple-darwin"
    inner_dir.mkdir(parents=True)
    _ = (inner_dir / "uv").write_text("#!/bin/sh\n", encoding="utf-8")
    _ = (inner_dir / "uvx").write_text("#!/bin/sh\n", encoding="utf-8")
    tar_path = cfg.cache_dir / "uv-aarch64-apple-darwin.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(inner_dir, arcname="uv-aarch64-apple-darwin")

    with (
        patch.object(uv, "common_download_file", return_value=True),
        patch.object(
            uv,
            "detect_platform_archive",
            return_value=("uv-aarch64-apple-darwin.tar.gz", "tar.gz"),
        ),
    ):
        extracted = uv.download_and_extract_uv("0.12.5", cfg)
        assert extracted == cfg.cache_dir / "0.12.5"
        assert (extracted / "uv").exists()
        assert (extracted / "uvx").exists()

    # Extraction of zip format
    zip_path = cfg.cache_dir / "uv-x86_64-pc-windows-msvc.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("uv.exe", "#!/bin/sh\n")
        zf.writestr("uvx.exe", "#!/bin/sh\n")

    with (
        patch.object(uv, "common_download_file", return_value=True),
        patch.object(
            uv,
            "detect_platform_archive",
            return_value=("uv-x86_64-pc-windows-msvc.zip", "zip"),
        ),
    ):
        extracted_zip = uv.download_and_extract_uv("0.12.5", cfg)
        assert extracted_zip == cfg.cache_dir / "0.12.5"
        assert (extracted_zip / "uv.exe").exists()


def test_create_launcher_shims(tmp_path: Path) -> None:
    """Test launcher shim creation for uv and uvx."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    ver_dir = tmp_path / "cache" / "0.12.5"
    ver_dir.mkdir(parents=True)
    _ = (ver_dir / "uv").write_text("#!/bin/sh\n", encoding="utf-8")
    _ = (ver_dir / "uvx").write_text("#!/bin/sh\n", encoding="utf-8")

    shims = uv.create_launcher_shims(ver_dir, cfg)
    assert len(shims) == 2
    for shim in shims:
        assert shim.is_file()
        assert os.access(shim, os.X_OK)

    # Dry run
    cfg.dry_run = True
    dry_shims = uv.create_launcher_shims(ver_dir, cfg)
    assert len(dry_shims) == 2


def test_apply_version_link_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test applying and activating UV version link."""
    cfg = Config(
        install_dir=tmp_path / "install",
        cache_dir=tmp_path / "cache",
        bin_dir=tmp_path / "bin",
        man_dir=tmp_path / "man",
        yes=True,
    )
    ver_dir = cfg.cache_dir / "0.12.5"
    ver_dir.mkdir(parents=True)
    _ = (ver_dir / "uv").write_text("#!/bin/sh\n", encoding="utf-8")
    _ = (ver_dir / "uvx").write_text("#!/bin/sh\n", encoding="utf-8")

    # Rejection prompt abort
    cfg_no = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", yes=False
    )
    with patch("typer.confirm", return_value=False), pytest.raises(typer.Exit):
        uv.apply_version_link("0.12.5", cfg_no)

    # Dry run execution
    cfg_dry = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", dry_run=True
    )
    with patch.object(uv, "download_and_extract_uv", return_value=ver_dir):
        uv.apply_version_link("0.12.5", cfg_dry)

    # Existing active link directory removal before symlink creation
    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    cfg.current_link.mkdir(parents=True, exist_ok=True)
    with patch.object(uv, "download_and_extract_uv", return_value=ver_dir):
        uv.apply_version_link("0.12.5", cfg)
        assert cfg.current_link.is_symlink()

    # Existing active link file unlinking before symlink creation
    cfg.current_link.unlink()
    _ = cfg.current_link.write_text("", encoding="utf-8")
    with patch.object(uv, "download_and_extract_uv", return_value=ver_dir):
        uv.apply_version_link("0.12.5", cfg)
        assert cfg.current_link.is_symlink()

    # PATH notification
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    with patch.object(uv, "download_and_extract_uv", return_value=ver_dir):
        uv.apply_version_link("0.12.5", cfg)


def test_render_versions_table_and_status(tmp_path: Path) -> None:
    """Test rendering versions table and status display."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    cfg.cache_dir.mkdir(parents=True)
    (cfg.cache_dir / "0.12.5").mkdir()

    uv.render_versions_table(cfg)

    # Status when active version is None (not installed)
    with (
        patch.object(uv, "get_installed_version", return_value=None),
        patch.object(uv, "get_latest_github_version", return_value="0.12.5"),
        patch.object(uv, "get_min_uv_version", return_value="0.11.0"),
    ):
        uv.render_status(cfg)

    # Status when active version is installed and up to date
    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    cfg.current_link.symlink_to(cfg.cache_dir / "0.12.5")
    with (
        patch.object(uv, "get_installed_version", return_value="0.12.5"),
        patch.object(uv, "get_latest_github_version", return_value="0.12.5"),
        patch.object(uv, "get_min_uv_version", return_value="0.11.0"),
    ):
        uv.render_status(cfg)

    # Status when active version is below minimum requirement
    with (
        patch.object(uv, "get_installed_version", return_value="0.10.0"),
        patch.object(uv, "get_latest_github_version", return_value="0.12.5"),
        patch.object(uv, "get_min_uv_version", return_value="0.11.0"),
    ):
        uv.render_status(cfg)


def test_clean_cache_and_uninstall(tmp_path: Path) -> None:
    """Test clean_cache and uninstall_uv routines."""
    cfg = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", yes=True
    )
    cfg.cache_dir.mkdir(parents=True)
    cfg.bin_dir.mkdir(parents=True)

    unused = cfg.cache_dir / "0.11.0"
    unused.mkdir()
    unused_file = cfg.cache_dir / "temp.tar.gz"
    _ = unused_file.write_text("", encoding="utf-8")
    active = cfg.cache_dir / "0.12.5"
    active.mkdir()
    cfg.install_dir.mkdir(parents=True)
    cfg.current_link.symlink_to(active)

    # Clean dry-run
    cfg.dry_run = True
    assert uv.clean_cache(cfg) == 2
    cfg.dry_run = False

    _ = (cfg.cache_dir / "current").write_text("", encoding="utf-8")
    removed = uv.clean_cache(cfg)
    assert removed == 2
    assert not unused.exists()
    assert not unused_file.exists()
    assert active.exists()

    _ = (cfg.bin_dir / "uv").write_text("", encoding="utf-8")
    _ = (cfg.cache_dir / "purge_file.tar.gz").write_text("", encoding="utf-8")

    shims, link, cache = uv.uninstall_uv(cfg, purge=True)
    assert len(shims) >= 1
    assert link is not None
    assert len(cache) >= 1

    # Test uninstall when current link is a directory
    cfg.current_link.mkdir(parents=True, exist_ok=True)
    _, removed_link, _ = uv.uninstall_uv(cfg)
    assert removed_link == cfg.current_link


def test_get_config_from_context_overrides(tmp_path: Path) -> None:
    """Test get_config_from_context options override."""
    ctx = typer.Context(typer.main.get_command(app))
    ctx.obj = Config(tmp_path / "1", tmp_path / "2", tmp_path / "3", tmp_path / "4")

    cfg = uv.get_config_from_context(
        ctx,
        verbose=True,
        dry_run=True,
        force=True,
        yes=True,
        dir_path=tmp_path / "custom_d",
        cache_dir=tmp_path / "custom_c",
        bin_dir=tmp_path / "custom_b",
        man_dir=tmp_path / "custom_m",
    )
    assert cfg.verbose is True
    assert cfg.dry_run is True
    assert cfg.force is True
    assert cfg.yes is True
    assert cfg.install_dir == tmp_path / "custom_d"
    assert cfg.cache_dir == tmp_path / "custom_c"
    assert cfg.bin_dir == tmp_path / "custom_b"
    assert cfg.man_dir == tmp_path / "custom_m"

    # Context without initial obj
    ctx_empty = typer.Context(typer.main.get_command(app))
    ctx_empty.obj = None
    cfg_empty = uv.get_config_from_context(ctx_empty)
    assert ctx_empty.obj == cfg_empty


def test_render_which(tmp_path: Path) -> None:
    """Test render_which output."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    uv.render_which(cfg)


def test_cli_commands(tmp_path: Path) -> None:
    """Test all Typer CLI command entry points."""
    opts = [
        "--dir",
        str(tmp_path / "install"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--bin-dir",
        str(tmp_path / "bin"),
        "--man-dir",
        str(tmp_path / "man"),
    ]

    res_version = runner.invoke(app, ["--version"])
    assert res_version.exit_code == 0

    res_self_ver = runner.invoke(app, ["self", "version", "--short"])
    assert res_self_ver.exit_code == 0

    res_self_ver_long = runner.invoke(app, ["self", "version"])
    assert res_self_ver_long.exit_code == 0

    res_self_path = runner.invoke(app, ["self", "path"])
    assert res_self_path.exit_code == 0

    res_help = runner.invoke(app, ["help", "install"])
    assert res_help.exit_code == 0

    res_no_subcmd = runner.invoke(app, [*opts])
    assert res_no_subcmd.exit_code == 0

    res_status = runner.invoke(app, [*opts, "status"])
    assert res_status.exit_code == 0

    res_which = runner.invoke(app, [*opts, "which"])
    assert res_which.exit_code == 0

    res_versions = runner.invoke(app, [*opts, "versions"])
    assert res_versions.exit_code == 0

    res_clean_abort = runner.invoke(app, [*opts, "clean"], input="n\n")
    assert res_clean_abort.exit_code == 0

    res_clean = runner.invoke(app, [*opts, "clean", "-y", "-n"])
    assert res_clean.exit_code == 0

    res_clean_act = runner.invoke(app, [*opts, "clean", "-y"])
    assert res_clean_act.exit_code == 0

    res_rehash_missing = runner.invoke(app, [*opts, "rehash"])
    assert res_rehash_missing.exit_code == 0

    # Active installation rehash
    active_d = tmp_path / "cache" / "0.12.5"
    active_d.mkdir(parents=True, exist_ok=True)
    _ = (active_d / "uv").write_text("", encoding="utf-8")
    (tmp_path / "install").mkdir(parents=True, exist_ok=True)
    (tmp_path / "install" / "current").symlink_to(active_d)
    res_rehash_act = runner.invoke(app, [*opts, "rehash"])
    assert res_rehash_act.exit_code == 0

    res_install_dry = runner.invoke(app, [*opts, "install", "0.12.5", "-y", "-n"])
    assert res_install_dry.exit_code == 0

    res_install_latest = runner.invoke(app, [*opts, "install", "-y", "-n"])
    assert res_install_latest.exit_code == 0

    res_update_dry = runner.invoke(app, [*opts, "update", "-y", "-n"])
    assert res_update_dry.exit_code == 0

    with (
        patch.object(uv, "get_installed_version", return_value="0.11.0"),
        patch.object(uv, "get_latest_github_version", return_value="0.12.5"),
        patch.object(uv, "apply_version_link") as mock_apply,
    ):
        res_update_act = runner.invoke(app, [*opts, "update", "-y"])
        assert res_update_act.exit_code == 0
        mock_apply.assert_called_once_with("0.12.5", mock_apply.call_args[0][1])

    res_use_dry = runner.invoke(app, [*opts, "use", "0.12.5", "-y", "-n"])
    assert res_use_dry.exit_code == 0

    res_uninstall_abort = runner.invoke(app, [*opts, "uninstall"], input="n\n")
    assert res_uninstall_abort.exit_code == 0

    res_uninstall_dry = runner.invoke(app, [*opts, "uninstall", "-y", "-n"])
    assert res_uninstall_dry.exit_code == 0

    res_uninstall_act = runner.invoke(app, [*opts, "uninstall", "--purge", "-y"])
    assert res_uninstall_act.exit_code == 0


def test_cmd_exec_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test cmd_exec execution, option parsing, and error conditions."""
    opts = [
        "--dir",
        str(tmp_path / "install"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--bin-dir",
        str(tmp_path / "bin"),
        "--man-dir",
        str(tmp_path / "man"),
    ]

    ver_dir = tmp_path / "cache" / "0.12.5"
    ver_dir.mkdir(parents=True)
    _ = (ver_dir / "uv").write_text("#!/bin/sh\n", encoding="utf-8")

    # Missing command error
    res_no_cmd = runner.invoke(app, [*opts, "exec"])
    assert res_no_cmd.exit_code != 0

    # Exec with --use
    with (
        patch.object(uv, "download_and_extract_uv", return_value=ver_dir),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec = runner.invoke(app, [*opts, "exec", "--use", "0.12.5", "echo", "hello"])
        assert res_exec.exit_code == 0

    # Exec with --use-version
    monkeypatch.setattr(
        sys, "argv", ["install-uv", "exec", "--use-version", "0.12.5", "echo", "hello"]
    )
    with (
        patch.object(uv, "download_and_extract_uv", return_value=ver_dir),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec_ver = runner.invoke(
            app, [*opts, "exec", "--use-version", "0.12.5", "echo", "hello"]
        )
        assert res_exec_ver.exit_code == 0

    # Exec with --use=...
    monkeypatch.setattr(sys, "argv", ["install-uv", "exec", "--use=0.12.5", "-v", "echo", "hello"])
    with (
        patch.object(uv, "download_and_extract_uv", return_value=ver_dir),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec_eq = runner.invoke(app, [*opts, "exec", "--use=0.12.5", "-v", "echo", "hello"])
        assert res_exec_eq.exit_code == 0

    # Exec when current link is missing
    (tmp_path / "install" / "current").unlink(missing_ok=True)
    monkeypatch.setattr(sys, "argv", ["install-uv", "exec", "echo", "hello"])
    with (
        patch.object(uv, "download_and_extract_uv", return_value=ver_dir),
        patch.object(uv, "apply_version_link"),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec_latest = runner.invoke(app, [*opts, "exec", "echo", "hello"])
        assert res_exec_latest.exit_code == 0

    # Exec with existing link
    (tmp_path / "install").mkdir(parents=True, exist_ok=True)
    (tmp_path / "install" / "current").symlink_to(ver_dir)
    with patch(
        "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
    ):
        res_exec_link = runner.invoke(app, [*opts, "exec", "echo", "hello"])
        assert res_exec_link.exit_code == 0

    # Exec subprocess error
    with patch("subprocess.run", side_effect=OSError("Exec error")):
        res_exec_err = runner.invoke(app, [*opts, "exec", "invalid_bin"])
        assert res_exec_err.exit_code != 0


def test_main_entrypoint() -> None:
    """Test top-level main function."""
    with patch.object(uv, "app", side_effect=Exception("Test error")), pytest.raises(typer.Exit):
        uv.main()

    with patch.object(uv, "app"):
        uv.main()
