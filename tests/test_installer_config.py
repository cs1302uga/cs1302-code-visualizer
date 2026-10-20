"""Installer configuration must work in wheels and standalone source checkouts."""

import pytest

from scripts.installer import common


@pytest.fixture
def installed_layout(tmp_path, monkeypatch):
    site_packages = tmp_path / "installed" / "site-packages"
    module = site_packages / "scripts" / "installer" / "common.py"
    module.parent.mkdir(parents=True)
    module.touch()
    package = site_packages / "cs1302_code_visualizer"
    package.mkdir()
    (package / "_tracer.toml").write_text(
        '[project]\nversion = "7.8.9"\n'
        "[tool.cs1302book.system-dependencies]\n"
        'system-dependencies = ["enchant>=2.8.0,<3", "jdk>=25,<26", "uv>=0.11.0"]\n'
    )
    monkeypatch.setattr(common, "__file__", str(module))
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    return site_packages, caller


def test_installed_metadata_and_dependencies_without_caller_project(installed_layout):
    _, caller = installed_layout
    assert common.find_project_root() == caller
    assert common.get_project_version(caller) == "7.8.9"
    assert common.get_configured_dependencies(caller) == {
        "enchant": "2.8.0",
        "jdk": "25",
        "uv": "0.11.0",
    }
    assert common.get_min_system_dependency_version(caller, "uv") == "0.11.0"


def test_installed_commands_respect_caller_project_configuration(installed_layout, monkeypatch):
    _, caller = installed_layout
    (caller / "pyproject.toml").write_text(
        '[project]\nversion = "1.2.3"\n'
        "[tool.cs1302book.system-dependencies]\n"
        'system-dependencies = ["graphviz>=99", "jdk==42", "uv"]\n'
    )
    nested = caller / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert common.find_project_root() == caller
    assert common.get_project_version(caller) == "1.2.3"
    assert common.get_configured_dependencies(caller) == {
        "graphviz": "99",
        "jdk": "42",
        "uv": "latest",
    }
    assert common.get_min_system_dependency_version(caller, "jdk") == "42"
    assert common.get_min_system_dependency_version(caller, "enchant") is None


@pytest.mark.parametrize("contents", ["[project]\nname = 'caller'\n", "invalid = ["])
def test_missing_or_unreadable_caller_settings_use_packaged_defaults(installed_layout, contents):
    _, caller = installed_layout
    (caller / "pyproject.toml").write_text(contents)
    assert common.get_project_version(caller) == "7.8.9"
    assert common.get_configured_dependencies(caller)["enchant"] == "2.8.0"


def test_explicit_empty_caller_dependencies_remain_empty(installed_layout):
    _, caller = installed_layout
    (caller / "pyproject.toml").write_text(
        "[tool.cs1302book.system-dependencies]\nsystem-dependencies = []\n"
    )
    assert common.get_configured_dependencies(caller) == {}
    assert common.get_min_system_dependency_version(caller, "jdk") is None


def test_installed_layout_does_not_discover_unrelated_parent_project(installed_layout):
    site_packages, caller = installed_layout
    (site_packages.parent / "pyproject.toml").write_text('[project]\nversion = "99.99.99"\n')
    assert common.find_project_root() == caller
    assert common.get_project_version(caller) == "7.8.9"


def test_standalone_source_fallback_uses_checkout_config(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    module = root / "scripts" / "installer" / "common.py"
    module.parent.mkdir(parents=True)
    module.touch()
    (root / "pyproject.toml").write_text(
        '[project]\nversion = "4.5.6"\n'
        '[tool.cs1302book.system-dependencies]\nsystem-dependencies = ["graphviz>=15"]\n'
    )
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.setattr(common, "__file__", str(module))
    monkeypatch.chdir(caller)
    assert common.find_project_root() == root
    assert common.get_project_version(caller) == "4.5.6"
    assert common.get_configured_dependencies(caller) == {"graphviz": "15"}


def test_explicit_start_directory_search_is_preserved(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "3.2.1"\n')
    nested = tmp_path / "nested"
    nested.mkdir()
    assert common.find_project_root(nested) == tmp_path


def test_distribution_metadata_fallback_without_configuration(installed_layout, monkeypatch):
    site_packages, caller = installed_layout
    (site_packages / "cs1302_code_visualizer" / "_tracer.toml").unlink()
    monkeypatch.setattr(common, "version", lambda name: "8.9.10")
    assert common.get_project_version(caller) == "8.9.10"
    assert common.get_configured_dependencies(caller) == {}


def test_unconfigured_standalone_copy_has_no_invented_version(installed_layout, monkeypatch):
    site_packages, caller = installed_layout
    (site_packages / "cs1302_code_visualizer" / "_tracer.toml").unlink()

    def missing_distribution(name):
        raise common.PackageNotFoundError(name)

    monkeypatch.setattr(common, "version", missing_distribution)
    assert common.get_project_version(caller) == "unknown"
