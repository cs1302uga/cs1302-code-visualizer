"""Unit tests for the system dependencies manager script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from scripts import install_deps
from scripts.install_deps import (
    DependencyInfo,
    DepStatus,
    app,
    collect_all_dependencies_status,
    execute_dependency_install,
    inspect_dependency,
    render_dependencies_table,
    run_interactive_install,
)
from scripts.installer import enchant, graphviz, jdk, plantuml, uv

runner = CliRunner()


def test_dep_status_enum_and_dependency_info_properties() -> None:
    """Test DependencyInfo properties across different DepStatus states."""
    info_up = DependencyInfo("uv", "0.12.5", "0.11.0", "0.12.5", DepStatus.UP_TO_DATE)
    assert "Up to date" in info_up.status_label
    assert not info_up.needs_install

    info_upd = DependencyInfo("uv", "0.11.0", "0.11.0", "0.12.5", DepStatus.UPDATE_AVAILABLE)
    assert "Update available" in info_upd.status_label
    assert not info_upd.needs_install

    info_low = DependencyInfo("uv", "0.10.0", "0.11.0", "0.12.5", DepStatus.BELOW_MIN)
    assert "Outdated" in info_low.status_label
    assert info_low.needs_install

    info_none = DependencyInfo("uv", None, "0.11.0", "0.12.5", DepStatus.NOT_INSTALLED)
    assert "Not installed" in info_none.status_label
    assert info_none.needs_install


def test_inspect_dependency(tmp_path: Path) -> None:
    """Test inspect_dependency for enchant, graphviz, plantuml, jdk, and uv."""
    cfg_g = graphviz.create_default_config(dir_path=tmp_path / "g")
    cfg_p = plantuml.create_default_config(dir_path=tmp_path / "p")
    cfg_j = jdk.create_default_config(dir_path=tmp_path / "j")
    cfg_e = enchant.create_default_config(dir_path=tmp_path / "e")
    cfg_u = uv.create_default_config(dir_path=tmp_path / "u")

    with (
        patch.object(enchant, "get_installed_version", return_value="2.8.19"),
        patch.object(enchant, "get_latest_github_version", return_value="2.8.19"),
    ):
        info_e = inspect_dependency("enchant", "2.8.0", cfg_g, cfg_p, cfg_j, cfg_e, cfg_u)
        assert info_e.status == DepStatus.UP_TO_DATE
        assert info_e.installed_version == "2.8.19"

    with (
        patch.object(graphviz, "get_installed_version", return_value=None),
        patch.object(graphviz, "get_latest_gitlab_version", return_value="16.0.0"),
    ):
        info_g = inspect_dependency("graphviz", "15.1.0", cfg_g, cfg_p, cfg_j, cfg_e, cfg_u)
        assert info_g.status == DepStatus.NOT_INSTALLED

    with (
        patch.object(plantuml, "get_installed_version", return_value="1.2025.0"),
        patch.object(plantuml, "get_latest_github_version", return_value="1.2026.6"),
    ):
        info_p = inspect_dependency("plantuml", "1.2026.1", cfg_g, cfg_p, cfg_j, cfg_e, cfg_u)
        assert info_p.status == DepStatus.BELOW_MIN

    with (
        patch.object(jdk, "get_installed_version", return_value="25.0.3"),
        patch.object(jdk, "get_latest_jdk_version", return_value="25.0.4"),
    ):
        info_j = inspect_dependency("jdk", "25", cfg_g, cfg_p, cfg_j, cfg_e, cfg_u)
        assert info_j.status == DepStatus.UPDATE_AVAILABLE

    with (
        patch.object(uv, "get_installed_version", side_effect=[None, None, "0.12.5"]),
        patch("shutil.which", return_value="/usr/local/bin/uv"),
        patch.object(uv, "get_latest_github_version", return_value="0.12.5"),
    ):
        info_u = inspect_dependency("uv", "0.11.0", cfg_g, cfg_p, cfg_j, cfg_e, cfg_u)
        assert info_u.status == DepStatus.UP_TO_DATE
        assert info_u.installed_version == "0.12.5"


def test_collect_all_dependencies_status(tmp_path: Path) -> None:
    """Test collecting dependency statuses with filtering."""
    cfg_g = graphviz.create_default_config(dir_path=tmp_path / "g")
    cfg_p = plantuml.create_default_config(dir_path=tmp_path / "p")
    cfg_j = jdk.create_default_config(dir_path=tmp_path / "j")
    cfg_e = enchant.create_default_config(dir_path=tmp_path / "e")
    cfg_u = uv.create_default_config(dir_path=tmp_path / "u")

    def mock_inspect(name: str, req: str | None, *args: object) -> DependencyInfo:
        _ = args
        return DependencyInfo(name, req, req, req, DepStatus.UP_TO_DATE)

    with (
        patch.object(
            install_deps,
            "get_configured_dependencies",
            return_value={"enchant": "2.8.0", "graphviz": "15.1.0", "uv": "0.11.0"},
        ),
        patch.object(
            install_deps,
            "inspect_dependency",
            side_effect=mock_inspect,
        ),
    ):
        infos = collect_all_dependencies_status(tmp_path, cfg_g, cfg_p, cfg_j, cfg_e, cfg_u)
        assert len(infos) == 3

        filtered = collect_all_dependencies_status(
            tmp_path, cfg_g, cfg_p, cfg_j, cfg_e, cfg_u, ["uv"]
        )
        assert len(filtered) == 1
        assert filtered[0].name == "uv"


def test_render_dependencies_table() -> None:
    """Test rendering rich table of dependency infos."""
    infos = [
        DependencyInfo("enchant", "2.8.19", "2.8.0", "2.8.19", DepStatus.UP_TO_DATE),
        DependencyInfo("uv", None, "0.11.0", "0.12.5", DepStatus.NOT_INSTALLED),
    ]
    render_dependencies_table(infos)


def test_execute_dependency_install(tmp_path: Path) -> None:
    """Test executing installation for all dependency types."""
    cfg_g = graphviz.create_default_config(dir_path=tmp_path / "g")
    cfg_p = plantuml.create_default_config(dir_path=tmp_path / "p")
    cfg_j = jdk.create_default_config(dir_path=tmp_path / "j")
    cfg_e = enchant.create_default_config(dir_path=tmp_path / "e")
    cfg_u = uv.create_default_config(dir_path=tmp_path / "u")

    with (
        patch.object(enchant, "apply_version_link") as mock_e,
        patch.object(graphviz, "apply_version_link") as mock_g,
        patch.object(plantuml, "apply_version_link") as mock_p,
        patch.object(jdk, "apply_version_link") as mock_j,
        patch.object(uv, "apply_version_link") as mock_u,
    ):
        execute_dependency_install(
            DependencyInfo("enchant", None, "2.8.0", "2.8.19", DepStatus.NOT_INSTALLED),
            None,
            cfg_g,
            cfg_p,
            cfg_j,
            cfg_e,
            cfg_u,
        )
        mock_e.assert_called_once()

        execute_dependency_install(
            DependencyInfo("graphviz", None, "15.1.0", "16.0.0", DepStatus.NOT_INSTALLED),
            "16.0.0",
            cfg_g,
            cfg_p,
            cfg_j,
            cfg_e,
            cfg_u,
        )
        mock_g.assert_called_once()

        execute_dependency_install(
            DependencyInfo("plantuml", None, "1.2026.1", "1.2026.6", DepStatus.NOT_INSTALLED),
            None,
            cfg_g,
            cfg_p,
            cfg_j,
            cfg_e,
            cfg_u,
        )
        mock_p.assert_called_once()

        execute_dependency_install(
            DependencyInfo("jdk", None, "25", "25.0.4", DepStatus.NOT_INSTALLED),
            None,
            cfg_g,
            cfg_p,
            cfg_j,
            cfg_e,
            cfg_u,
        )
        mock_j.assert_called_once()

        execute_dependency_install(
            DependencyInfo("uv", None, "0.11.0", "0.12.5", DepStatus.NOT_INSTALLED),
            None,
            cfg_g,
            cfg_p,
            cfg_j,
            cfg_e,
            cfg_u,
        )
        mock_u.assert_called_once()


def test_run_interactive_install(tmp_path: Path) -> None:
    """Test interactive install logic when dependencies are satisfied vs missing."""
    cfg_g = graphviz.create_default_config(dir_path=tmp_path / "g")
    cfg_p = plantuml.create_default_config(dir_path=tmp_path / "p")
    cfg_j = jdk.create_default_config(dir_path=tmp_path / "j")
    cfg_e = enchant.create_default_config(dir_path=tmp_path / "e")
    cfg_u = uv.create_default_config(dir_path=tmp_path / "u")

    all_satisfied = [DependencyInfo("uv", "0.12.5", "0.11.0", "0.12.5", DepStatus.UP_TO_DATE)]
    run_interactive_install(
        all_satisfied,
        force=False,
        yes=True,
        cfg_graphviz=cfg_g,
        cfg_plantuml=cfg_p,
        cfg_jdk=cfg_j,
        cfg_enchant=cfg_e,
        cfg_uv=cfg_u,
    )

    missing = [DependencyInfo("uv", None, "0.11.0", "0.12.5", DepStatus.NOT_INSTALLED)]
    with patch.object(install_deps, "execute_dependency_install") as mock_exec:
        run_interactive_install(
            missing,
            force=False,
            yes=True,
            cfg_graphviz=cfg_g,
            cfg_plantuml=cfg_p,
            cfg_jdk=cfg_j,
            cfg_enchant=cfg_e,
            cfg_uv=cfg_u,
        )
        mock_exec.assert_called_once()

    # Prompt skipped by user
    with (
        patch("typer.confirm", return_value=False),
        patch.object(install_deps, "execute_dependency_install") as mock_exec_skip,
    ):
        run_interactive_install(
            missing,
            force=False,
            yes=False,
            cfg_graphviz=cfg_g,
            cfg_plantuml=cfg_p,
            cfg_jdk=cfg_j,
            cfg_enchant=cfg_e,
            cfg_uv=cfg_u,
        )
        mock_exec_skip.assert_not_called()


def test_cli_version_callback() -> None:
    """Test cli_version_callback."""
    with pytest.raises(typer.Exit):
        install_deps.cli_version_callback(True)


def test_install_deps_cli_commands(tmp_path: Path) -> None:
    """Test install-deps CLI commands and options."""
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

    res_ver = runner.invoke(app, ["--version"])
    assert res_ver.exit_code == 0

    res_self_ver = runner.invoke(app, ["self", "version", "--short"])
    assert res_self_ver.exit_code == 0

    res_self_ver_long = runner.invoke(app, ["self", "version"])
    assert res_self_ver_long.exit_code == 0

    res_self_path = runner.invoke(app, ["self", "path"])
    assert res_self_path.exit_code == 0

    res_help = runner.invoke(app, ["help", "install"])
    assert res_help.exit_code == 0

    with patch.object(install_deps, "collect_all_dependencies_status", return_value=[]):
        res_root = runner.invoke(app, [*opts, "-y", "-n"])
        assert res_root.exit_code == 0

        res_status = runner.invoke(app, [*opts, "status"])
        assert res_status.exit_code == 0

        res_which = runner.invoke(app, [*opts, "which"])
        assert res_which.exit_code == 0

        res_clean = runner.invoke(app, [*opts, "clean", "-y", "-n"])
        assert res_clean.exit_code == 0

        res_rehash = runner.invoke(app, [*opts, "rehash", "--all", "-n"])
        assert res_rehash.exit_code == 0

        res_rehash_single = runner.invoke(app, [*opts, "rehash", "uv", "-n"])
        assert res_rehash_single.exit_code == 0

        res_update = runner.invoke(app, [*opts, "update", "-n", "-y"])
        assert res_update.exit_code == 0

        res_install = runner.invoke(app, [*opts, "install", "-n", "-y"])
        assert res_install.exit_code == 0

        res_uninstall = runner.invoke(app, [*opts, "uninstall", "-n", "-y"])
        assert res_uninstall.exit_code == 0


def test_install_deps_update_and_uninstall_flows(tmp_path: Path) -> None:
    """Test interactive prompt rejection and uninstallation of dependencies."""
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

    infos = [
        DependencyInfo("graphviz", "15.1.0", "15.1.0", "16.0.0", DepStatus.UPDATE_AVAILABLE),
        DependencyInfo("plantuml", "1.2026.1", "1.2026.1", "1.2026.6", DepStatus.UPDATE_AVAILABLE),
        DependencyInfo("enchant", "2.8.19", "2.8.0", "2.8.19", DepStatus.UPDATE_AVAILABLE),
        DependencyInfo("jdk", "25.0.3", "25", "25.0.4", DepStatus.UPDATE_AVAILABLE),
        DependencyInfo("uv", "0.11.17", "0.11.0", "0.12.5", DepStatus.UPDATE_AVAILABLE),
    ]

    # Test skipping on update and uninstall
    with (
        patch.object(install_deps, "collect_all_dependencies_status", return_value=infos),
        patch("typer.confirm", return_value=False),
    ):
        res_update_skip = runner.invoke(app, [*opts, "update"])
        assert res_update_skip.exit_code == 0

        res_uninst_skip = runner.invoke(app, [*opts, "uninstall"])
        assert res_uninst_skip.exit_code == 0

    # Test executing update and uninstall across all 5 dependencies
    with (
        patch.object(install_deps, "collect_all_dependencies_status", return_value=infos),
        patch("typer.confirm", return_value=True),
        patch.object(graphviz, "apply_version_link"),
        patch.object(plantuml, "apply_version_link"),
        patch.object(enchant, "apply_version_link"),
        patch.object(jdk, "apply_version_link"),
        patch.object(uv, "apply_version_link"),
        patch.object(graphviz, "uninstall_graphviz"),
        patch.object(plantuml, "uninstall_plantuml"),
        patch.object(enchant, "uninstall_enchant", return_value=([], None, [], [])),
        patch.object(jdk, "uninstall_jdk"),
        patch.object(uv, "uninstall_uv", return_value=([], None, [])),
    ):
        res_update_all = runner.invoke(app, [*opts, "update", "-y"])
        assert res_update_all.exit_code == 0

        res_uninst_all = runner.invoke(app, [*opts, "uninstall", "-y"])
        assert res_uninst_all.exit_code == 0


def test_main_entrypoint() -> None:
    """Test top-level main function."""
    with (
        patch.object(install_deps, "app", side_effect=Exception("Test error")),
        pytest.raises(typer.Exit),
    ):
        install_deps.main()

    with patch.object(install_deps, "app"):
        install_deps.main()
