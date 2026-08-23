"""Unit tests for the Enchant standalone installer module."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import typer
from typer.testing import CliRunner

from scripts.installer import enchant
from scripts.installer.enchant import Config, app

runner = CliRunner()


def test_get_min_enchant_version(tmp_path: Path) -> None:
    """Test reading minimum enchant version from pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    _ = pyproject.write_text(
        '[tool.cs1302book.system-dependencies]\nsystem-dependencies = ["enchant>=2.8.0,<3"]\n',
        encoding="utf-8",
    )
    ver = enchant.get_min_enchant_version(tmp_path)
    assert ver == "2.8.0"


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
    assert cfg.primary_executable == tmp_path / "bin" / "enchant"

    with patch.object(enchant.err_console, "print") as mock_print:
        cfg.log("Test verbose message")
        mock_print.assert_called_once()

    cfg.verbose = False
    with patch.object(enchant.err_console, "print") as mock_print_silent:
        cfg.log("Silent message")
        mock_print_silent.assert_not_called()


def test_resolve_default_paths(tmp_path: Path) -> None:
    """Test default directory path resolution."""
    install_d, cache_d, bin_d, man_d = enchant.resolve_default_paths(tmp_path)
    assert install_d == tmp_path / "scripts" / "cache" / "enchant"
    assert cache_d == tmp_path / "scripts" / "cache" / "enchant"
    assert bin_d.name == "bin"
    assert man_d.name == "man"


def test_create_default_config_environment_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test environment variable overrides in create_default_config."""
    monkeypatch.setenv("ENCHANT_INSTALL_DIR", str(tmp_path / "custom_install"))
    monkeypatch.setenv("ENCHANT_CACHE_DIR", str(tmp_path / "custom_cache"))
    monkeypatch.setenv("ENCHANT_BIN_DIR", str(tmp_path / "custom_bin"))
    monkeypatch.setenv("ENCHANT_MAN_DIR", str(tmp_path / "custom_man"))
    monkeypatch.setenv("VERBOSE", "1")

    cfg = enchant.create_default_config()
    assert cfg.install_dir == tmp_path / "custom_install"
    assert cfg.cache_dir == tmp_path / "custom_cache"
    assert cfg.bin_dir == tmp_path / "custom_bin"
    assert cfg.man_dir == tmp_path / "custom_man"
    assert cfg.verbose is True


def test_get_installed_version_nonexistent(tmp_path: Path) -> None:
    """Test version detection on nonexistent path returns None."""
    nonexistent = tmp_path / "does_not_exist"
    assert enchant.get_installed_version(nonexistent) is None


def test_get_installed_version_with_executable(tmp_path: Path) -> None:
    """Test detecting installed version via executable output on Darwin and Linux."""
    install_dir = tmp_path / "enchant_2.8.2"
    bin_dir = install_dir / "bin"
    lib_dir = install_dir / "lib"
    bin_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)
    exec_file = bin_dir / "enchant-2"
    _ = exec_file.write_text("#!/bin/sh\necho 'enchant-2 (Enchant) 2.8.2' >&2\n", encoding="utf-8")
    _ = exec_file.chmod(0o755)

    with (
        patch("platform.system", return_value="Linux"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[str(exec_file), "-v"],
            returncode=0,
            stdout="",
            stderr="enchant-2 (Enchant) 2.8.2",
        )
        ver = enchant.get_installed_version(install_dir)
        assert ver == "2.8.2"

    with (
        patch("platform.system", return_value="Darwin"),
        patch("subprocess.run") as mock_run_darwin,
    ):
        mock_run_darwin.return_value = subprocess.CompletedProcess(
            args=[str(exec_file), "-v"],
            returncode=0,
            stdout="",
            stderr="enchant-2 (Enchant) 2.8.2",
        )
        ver_darwin = enchant.get_installed_version(install_dir)
        assert ver_darwin == "2.8.2"


def test_get_installed_version_fallback_to_dirname(tmp_path: Path) -> None:
    """Test directory name regex fallback when binary execution fails."""
    install_dir = tmp_path / "2.8.1"
    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True)
    exec_file = bin_dir / "enchant"
    _ = exec_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    _ = exec_file.chmod(0o755)

    with patch("subprocess.run", side_effect=OSError("Execution failed")):
        ver = enchant.get_installed_version(install_dir)
        assert ver == "2.8.1"

    # Test when executable output fails and dirname has no version pattern
    no_num_dir = tmp_path / "nodigits"
    (no_num_dir / "bin").mkdir(parents=True)
    _ = (no_num_dir / "bin" / "enchant").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    _ = (no_num_dir / "bin" / "enchant").chmod(0o755)
    with patch("subprocess.run", side_effect=OSError("Exec error")):
        assert enchant.get_installed_version(no_num_dir) is None

    # Test fallback when no binary exists
    empty_dir = tmp_path / "2.8.0"
    empty_dir.mkdir()
    assert enchant.get_installed_version(empty_dir) == "2.8.0"

    # Test when name doesn't match
    unmatched_dir = tmp_path / "no_ver_dir"
    unmatched_dir.mkdir()
    assert enchant.get_installed_version(unmatched_dir) is None


def test_get_latest_github_version_success() -> None:
    """Test fetching latest version tag from GitHub API."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"prerelease": True, "tag_name": "v3.0.0-alpha"},
        {"prerelease": False, "draft": False, "tag_name": "v2.8.2"},
    ]
    with patch("requests.get", return_value=mock_resp):
        ver = enchant.get_latest_github_version()
        assert ver == "2.8.2"


def test_get_latest_github_version_fallback() -> None:
    """Test fallback when GitHub API request fails."""
    with patch("requests.get", side_effect=requests.RequestException("Network down")):
        ver = enchant.get_latest_github_version()
        assert ver == enchant.DEFAULT_FALLBACK_VERSION


def test_get_github_release_versions_success() -> None:
    """Test fetching list of available release versions."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"prerelease": False, "draft": False, "tag_name": "v2.8.2"},
        {"prerelease": False, "draft": False, "tag_name": "v2.8.1"},
    ]
    with patch("requests.get", return_value=mock_resp):
        versions = enchant.get_github_release_versions()
        assert versions == ["2.8.2", "2.8.1"]


def test_get_github_release_versions_fallback() -> None:
    """Test fallback release versions list when API request fails."""
    with patch("requests.get", side_effect=requests.RequestException("Network down")):
        versions = enchant.get_github_release_versions()
        assert enchant.DEFAULT_FALLBACK_VERSION in versions


def test_resolve_target_tag(tmp_path: Path) -> None:
    """Test resolving target tag for 'latest' and explicit version strings."""
    cfg = Config(tmp_path, tmp_path, tmp_path, tmp_path)
    with patch.object(enchant, "get_latest_github_version", return_value="2.8.2"):
        tag, url = enchant.resolve_target_tag("latest", cfg)
        assert tag == "2.8.2"
        assert "2.8.2" in url

        tag_explicit, url_explicit = enchant.resolve_target_tag("v2.8.0", cfg)
        assert tag_explicit == "2.8.0"
        assert "2.8.0" in url_explicit


def test_download_and_build_enchant_already_installed(tmp_path: Path) -> None:
    """Test returning existing installed directory without rebuilding."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    ver_dir = cfg.cache_dir / "2.8.2"
    bin_dir = ver_dir / "bin"
    bin_dir.mkdir(parents=True)
    _ = (bin_dir / "enchant-2").write_text("", encoding="utf-8")

    with patch.object(enchant, "get_installed_version", return_value="2.8.2"):
        res = enchant.download_and_build_enchant("2.8.2", cfg)
        assert res == ver_dir


def test_download_and_build_enchant_dry_run(tmp_path: Path) -> None:
    """Test dry run execution for downloading and building."""
    cfg = Config(
        tmp_path / "install",
        tmp_path / "cache",
        tmp_path / "bin",
        tmp_path / "man",
        dry_run=True,
    )
    res = enchant.download_and_build_enchant("2.8.2", cfg)
    assert res == cfg.cache_dir / "2.8.2"


def test_download_and_build_enchant_full_build(tmp_path: Path) -> None:
    """Test full download, extract, configure, make, and make install lifecycle."""
    cfg = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", force=True
    )
    cfg.cache_dir.mkdir(parents=True)

    src_dir = tmp_path / "fake_src" / "other_name_dir"
    src_dir.mkdir(parents=True)
    _ = (src_dir / "configure").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tarball_path = cfg.cache_dir / "enchant-2.8.2.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(src_dir, arcname="other_name_dir")

    def mock_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "make" and len(cmd) > 1 and cmd[1] == "install":
            target_bin = cfg.cache_dir / "2.8.2" / "bin"
            target_bin.mkdir(parents=True, exist_ok=True)
            _ = (target_bin / "enchant-2").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with (
        patch.object(enchant, "common_download_file", return_value=True),
        patch("subprocess.run", side_effect=mock_run),
    ):
        target = enchant.download_and_build_enchant("2.8.2", cfg)
        assert target == cfg.cache_dir / "2.8.2"
        assert (target / "bin" / "enchant-2").exists()


def test_download_and_build_enchant_configure_script_missing(tmp_path: Path) -> None:
    """Test error raised when configure script is missing."""
    cfg = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", force=True
    )
    cfg.cache_dir.mkdir(parents=True)

    src_dir = tmp_path / "fake_src" / "enchant-2.8.2"
    src_dir.mkdir(parents=True)
    tarball_path = cfg.cache_dir / "enchant-2.8.2.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(src_dir, arcname="enchant-2.8.2")

    with (
        patch.object(enchant, "common_download_file", return_value=True),
        pytest.raises(typer.Exit),
    ):
        _ = enchant.download_and_build_enchant("2.8.2", cfg)


def test_download_and_build_enchant_configure_failure(tmp_path: Path) -> None:
    """Test failure during configure terminates with exit code 1."""
    cfg = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", force=True
    )
    cfg.cache_dir.mkdir(parents=True)

    src_dir = tmp_path / "fake_src" / "enchant-2.8.2"
    src_dir.mkdir(parents=True)
    _ = (src_dir / "configure").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    tarball_path = cfg.cache_dir / "enchant-2.8.2.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(src_dir, arcname="enchant-2.8.2")

    with (
        patch.object(enchant, "common_download_file", return_value=True),
        patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["./configure"], returncode=1, stderr="conf error"
            ),
        ),
        pytest.raises(typer.Exit),
    ):
        _ = enchant.download_and_build_enchant("2.8.2", cfg)


def test_download_and_build_enchant_make_and_make_install_failures(tmp_path: Path) -> None:
    """Test failure during make and make install terminates with exit code 1."""
    cfg = Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man", force=True
    )
    cfg.cache_dir.mkdir(parents=True)

    src_dir = tmp_path / "fake_src" / "enchant-2.8.2"
    src_dir.mkdir(parents=True)
    _ = (src_dir / "configure").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tarball_path = cfg.cache_dir / "enchant-2.8.2.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(src_dir, arcname="enchant-2.8.2")

    # Test make failure
    with (
        patch.object(enchant, "common_download_file", return_value=True),
        patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(args=["./configure"], returncode=0),
                subprocess.CompletedProcess(args=["make"], returncode=1, stderr="make error"),
            ],
        ),
        pytest.raises(typer.Exit),
    ):
        _ = enchant.download_and_build_enchant("2.8.2", cfg)

    # Test make install failure
    with (
        patch.object(enchant, "common_download_file", return_value=True),
        patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(args=["./configure"], returncode=0),
                subprocess.CompletedProcess(args=["make"], returncode=0),
                subprocess.CompletedProcess(
                    args=["make", "install"], returncode=1, stderr="install error"
                ),
            ],
        ),
        pytest.raises(typer.Exit),
    ):
        _ = enchant.download_and_build_enchant("2.8.2", cfg)


def test_create_launcher_shims_and_man_links(tmp_path: Path) -> None:
    """Test creation of executable launcher shims and man page symlinks."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    ver_dir = tmp_path / "cache" / "2.8.2"
    (ver_dir / "bin").mkdir(parents=True)
    _ = (ver_dir / "bin" / "enchant-2").write_text("#!/bin/sh\n", encoding="utf-8")
    _ = (ver_dir / "bin" / "enchant-lsmod-2").write_text("#!/bin/sh\n", encoding="utf-8")

    man_sec = ver_dir / "share" / "man" / "man1"
    man_sec.mkdir(parents=True)
    _ = (man_sec / "enchant-2.1").write_text(".TH ENCHANT 1\n", encoding="utf-8")

    shims = enchant.create_launcher_shims(ver_dir, cfg)
    assert len(shims) == 4
    for shim in shims:
        assert shim.is_file()
        assert os.access(shim, os.X_OK)

    man_links = enchant.create_man_links(ver_dir, cfg)
    assert len(man_links) == 1
    assert (cfg.man_dir / "man1" / "enchant-2.1").is_symlink()

    # Test recreating when target page already exists
    man_links_repeat = enchant.create_man_links(ver_dir, cfg)
    assert len(man_links_repeat) == 1

    # Test dry run creation
    cfg_dry = Config(
        tmp_path / "install",
        tmp_path / "cache",
        tmp_path / "bin",
        tmp_path / "man",
        dry_run=True,
    )
    dry_shims = enchant.create_launcher_shims(ver_dir, cfg_dry)
    assert len(dry_shims) == 4
    dry_man = enchant.create_man_links(ver_dir, cfg_dry)
    assert len(dry_man) == 1


def test_apply_version_link_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test applying and activating an Enchant version."""
    cfg = Config(
        install_dir=tmp_path / "install",
        cache_dir=tmp_path / "cache",
        bin_dir=tmp_path / "bin",
        man_dir=tmp_path / "man",
        yes=True,
    )
    ver_dir = cfg.cache_dir / "2.8.2"
    (ver_dir / "bin").mkdir(parents=True)
    _ = (ver_dir / "bin" / "enchant-2").write_text("", encoding="utf-8")
    man_sec = ver_dir / "share" / "man" / "man1"
    man_sec.mkdir(parents=True)
    _ = (man_sec / "enchant-2.1").write_text("", encoding="utf-8")

    # Test abort when confirmation is rejected
    cfg_no = Config(
        install_dir=tmp_path / "install",
        cache_dir=tmp_path / "cache",
        bin_dir=tmp_path / "bin",
        man_dir=tmp_path / "man",
        yes=False,
    )
    with (
        patch("typer.confirm", return_value=False),
        pytest.raises(typer.Exit),
    ):
        enchant.apply_version_link("2.8.2", cfg_no)

    # Test dry-run execution plan
    cfg_dry = Config(
        install_dir=tmp_path / "install",
        cache_dir=tmp_path / "cache",
        bin_dir=tmp_path / "bin",
        man_dir=tmp_path / "man",
        dry_run=True,
    )
    with patch.object(enchant, "download_and_build_enchant", return_value=ver_dir):
        enchant.apply_version_link("2.8.2", cfg_dry)

    # Test active link directory removal before symlink creation
    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    cfg.current_link.mkdir(parents=True, exist_ok=True)
    with patch.object(enchant, "download_and_build_enchant", return_value=ver_dir):
        enchant.apply_version_link("2.8.2", cfg)
        assert cfg.current_link.is_symlink()
        assert cfg.current_link.resolve() == ver_dir.resolve()

    # Test active link file unlinking before symlink creation
    cfg.current_link.unlink()
    _ = cfg.current_link.write_text("", encoding="utf-8")
    with patch.object(enchant, "download_and_build_enchant", return_value=ver_dir):
        enchant.apply_version_link("2.8.2", cfg)
        assert cfg.current_link.is_symlink()

    # Test notification when bin_dir is not in PATH
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    with patch.object(enchant, "download_and_build_enchant", return_value=ver_dir):
        enchant.apply_version_link("2.8.2", cfg)


def test_render_versions_table_and_status(tmp_path: Path) -> None:
    """Test rendering versions table and status display."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    cfg.cache_dir.mkdir(parents=True)
    (cfg.cache_dir / "2.8.2").mkdir()

    enchant.render_versions_table(cfg)

    # Status when active_ver is None (not installed)
    with (
        patch.object(enchant, "get_installed_version", return_value=None),
        patch.object(enchant, "get_latest_github_version", return_value="2.8.2"),
        patch.object(enchant, "get_min_enchant_version", return_value="2.8.0"),
    ):
        enchant.render_status(cfg)

    # Status when installed and satisfying minimum version
    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    cfg.current_link.symlink_to(cfg.cache_dir / "2.8.2")
    with (
        patch.object(enchant, "get_installed_version", return_value="2.8.2"),
        patch.object(enchant, "get_latest_github_version", return_value="2.8.2"),
        patch.object(enchant, "get_min_enchant_version", return_value="2.8.0"),
    ):
        enchant.render_status(cfg)

    # Status when active version is below minimum version
    with (
        patch.object(enchant, "get_installed_version", return_value="2.3.0"),
        patch.object(enchant, "get_latest_github_version", return_value="2.8.2"),
        patch.object(enchant, "get_min_enchant_version", return_value="2.8.0"),
    ):
        enchant.render_status(cfg)


def test_clean_cache_and_uninstall(tmp_path: Path) -> None:
    """Test cleaning unused cache and uninstallation."""
    cfg = Config(
        tmp_path / "install",
        tmp_path / "cache",
        tmp_path / "bin",
        tmp_path / "man",
        yes=True,
    )
    cfg.cache_dir.mkdir(parents=True)
    cfg.bin_dir.mkdir(parents=True)
    cfg.man_dir.mkdir(parents=True)

    unused = cfg.cache_dir / "2.8.0"
    unused.mkdir()
    unused_file = cfg.cache_dir / "temp.tar.gz"
    _ = unused_file.write_text("", encoding="utf-8")
    active = cfg.cache_dir / "2.8.2"
    active.mkdir()
    cfg.install_dir.mkdir(parents=True)
    cfg.current_link.symlink_to(active)

    # Test clean dry-run
    cfg.dry_run = True
    removed_dry = enchant.clean_cache(cfg)
    assert removed_dry == 2
    cfg.dry_run = False

    _ = (cfg.cache_dir / "current").write_text("", encoding="utf-8")
    removed = enchant.clean_cache(cfg)
    assert removed == 2
    assert not unused.exists()
    assert not unused_file.exists()
    assert active.exists()

    _ = (cfg.bin_dir / "enchant").write_text("", encoding="utf-8")
    man_sec = cfg.man_dir / "man1"
    man_sec.mkdir(parents=True)
    _ = (man_sec / "enchant.1").write_text("", encoding="utf-8")
    _ = (cfg.cache_dir / "purge_file.tar.gz").write_text("", encoding="utf-8")

    shims, link, cache, man = enchant.uninstall_enchant(cfg, purge=True)
    assert len(shims) >= 1
    assert link is not None
    assert len(cache) >= 1
    assert len(man) == 1

    # Test uninstalling when link is a directory (not symlink)
    cfg.current_link.mkdir(parents=True, exist_ok=True)
    _, removed_link, _, _ = enchant.uninstall_enchant(cfg)
    assert removed_link == cfg.current_link


def test_get_config_from_context_overrides(tmp_path: Path) -> None:
    """Test get_config_from_context options override."""
    ctx = typer.Context(typer.main.get_command(app))
    ctx.obj = Config(tmp_path / "1", tmp_path / "2", tmp_path / "3", tmp_path / "4")

    cfg = enchant.get_config_from_context(
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


def test_render_which(tmp_path: Path) -> None:
    """Test render_which location diagnostic output."""
    cfg = Config(tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man")
    enchant.render_which(cfg)


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

    res_status = runner.invoke(app, [*opts, "status"])
    assert res_status.exit_code == 0

    res_which = runner.invoke(app, [*opts, "which"])
    assert res_which.exit_code == 0

    res_versions = runner.invoke(app, [*opts, "versions"])
    assert res_versions.exit_code == 0

    res_clean = runner.invoke(app, [*opts, "clean", "-y", "-n"])
    assert res_clean.exit_code == 0

    res_clean_act = runner.invoke(app, [*opts, "clean", "-y"])
    assert res_clean_act.exit_code == 0

    res_rehash_missing = runner.invoke(app, [*opts, "rehash"])
    assert res_rehash_missing.exit_code == 0

    # Test rehash when active installation exists
    active_d = tmp_path / "cache" / "2.8.2"
    (active_d / "bin").mkdir(parents=True)
    _ = (active_d / "bin" / "enchant-2").write_text("", encoding="utf-8")
    (tmp_path / "install").mkdir(parents=True, exist_ok=True)
    (tmp_path / "install" / "current").symlink_to(active_d)
    res_rehash_act = runner.invoke(app, [*opts, "rehash"])
    assert res_rehash_act.exit_code == 0

    res_install_dry = runner.invoke(app, [*opts, "install", "2.8.2", "-y", "-n"])
    assert res_install_dry.exit_code == 0

    res_install_latest = runner.invoke(app, [*opts, "install", "-y", "-n"])
    assert res_install_latest.exit_code == 0

    res_update_dry = runner.invoke(app, [*opts, "update", "-y", "-n"])
    assert res_update_dry.exit_code == 0

    res_use_dry = runner.invoke(app, [*opts, "use", "2.8.2", "-y", "-n"])
    assert res_use_dry.exit_code == 0

    res_uninstall_abort = runner.invoke(app, [*opts, "uninstall"], input="n\n")
    assert res_uninstall_abort.exit_code == 0

    res_uninstall_dry = runner.invoke(app, [*opts, "uninstall", "-y", "-n"])
    assert res_uninstall_dry.exit_code == 0

    # Setup man page and link for uninstall report
    man_sec = tmp_path / "man" / "man1"
    man_sec.mkdir(parents=True, exist_ok=True)
    _ = (man_sec / "enchant.1").write_text("", encoding="utf-8")
    res_uninstall_act = runner.invoke(app, [*opts, "uninstall", "--purge", "-y"])
    assert res_uninstall_act.exit_code == 0


def test_cmd_exec_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test cmd_exec execution, flag parsing, and error conditions."""
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

    ver_dir = tmp_path / "cache" / "2.8.2"
    bin_dir = ver_dir / "bin"
    bin_dir.mkdir(parents=True)
    _ = (bin_dir / "enchant-2").write_text("#!/bin/sh\n", encoding="utf-8")

    # Missing command raises error
    res_no_cmd = runner.invoke(app, [*opts, "exec"])
    assert res_no_cmd.exit_code != 0

    # Test exec with --use
    with (
        patch.object(enchant, "download_and_build_enchant", return_value=ver_dir),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec = runner.invoke(app, [*opts, "exec", "--use", "2.8.2", "echo", "hello"])
        assert res_exec.exit_code == 0

    # Test exec with sys.argv containing --use-version
    monkeypatch.setattr(
        sys, "argv", ["install-enchant", "exec", "--use-version", "2.8.2", "echo", "hello"]
    )
    with (
        patch.object(enchant, "download_and_build_enchant", return_value=ver_dir),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec_ver = runner.invoke(
            app, [*opts, "exec", "--use-version", "2.8.2", "echo", "hello"]
        )
        assert res_exec_ver.exit_code == 0

    # Test exec on Linux with sys.argv containing --use=value
    monkeypatch.setattr(
        sys, "argv", ["install-enchant", "exec", "--use=2.8.2", "-v", "echo", "hello"]
    )
    with (
        patch("platform.system", return_value="Linux"),
        patch.object(enchant, "download_and_build_enchant", return_value=ver_dir),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec_linux = runner.invoke(app, [*opts, "exec", "--use=2.8.2", "-v", "echo", "hello"])
        assert res_exec_linux.exit_code == 0

    # Test exec when current_link does not exist
    (tmp_path / "install" / "current").unlink(missing_ok=True)
    monkeypatch.setattr(sys, "argv", ["install-enchant", "exec", "echo", "hello"])
    with (
        patch.object(enchant, "download_and_build_enchant", return_value=ver_dir),
        patch.object(enchant, "apply_version_link"),
        patch(
            "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
        ),
    ):
        res_exec_latest = runner.invoke(app, [*opts, "exec", "echo", "hello"])
        assert res_exec_latest.exit_code == 0

    # Test exec with existing link
    (tmp_path / "install").mkdir(parents=True, exist_ok=True)
    (tmp_path / "install" / "current").symlink_to(ver_dir)
    with patch(
        "subprocess.run", return_value=subprocess.CompletedProcess(args=["echo"], returncode=0)
    ):
        res_exec_link = runner.invoke(app, [*opts, "exec", "echo", "hello"])
        assert res_exec_link.exit_code == 0

    # Test exec subprocess failure handling
    with patch("subprocess.run", side_effect=OSError("Exec error")):
        res_exec_err = runner.invoke(app, [*opts, "exec", "invalid_bin"])
        assert res_exec_err.exit_code != 0


def test_main_entrypoint() -> None:
    """Test top-level main function."""
    with (
        patch.object(enchant, "app", side_effect=Exception("Test error")),
        pytest.raises(typer.Exit),
    ):
        enchant.main()

    with patch.object(enchant, "app"):
        enchant.main()
