"""Uninstall must not report a failed filesystem deletion as successful."""

from pathlib import Path

import pytest

from scripts.installer import graphviz, jdk, plantuml


@pytest.mark.parametrize("module", [graphviz, jdk, plantuml])
@pytest.mark.parametrize("target", ["launcher", "link", "cache_file", "cache_dir"])
def test_uninstall_propagates_deletion_failure(tmp_path, monkeypatch, module, target):
    kwargs = {name: tmp_path / name for name in ("install_dir", "cache_dir", "bin_dir")}
    if module is graphviz:
        kwargs["man_dir"] = tmp_path / "man_dir"
    for path in kwargs.values():
        path.mkdir()
    cfg = module.Config(**kwargs)
    if target == "launcher":
        path = cfg.wrapper_path if module is plantuml else cfg.primary_executable
        path.touch()
    elif target == "link":
        path = cfg.jar_symlink if module is plantuml else cfg.current_link
        path.symlink_to(tmp_path / "missing")
    else:
        path = cfg.cache_dir / "cached"
        if target == "cache_dir":
            path.mkdir()
        else:
            path.touch()

    def fail(*args, **kwargs):
        raise PermissionError("cannot delete")

    if target == "cache_dir":
        monkeypatch.setattr(module.shutil, "rmtree", fail)
    else:
        monkeypatch.setattr(Path, "unlink", fail)
    uninstall = getattr(module, f"uninstall_{module.__name__.split('.')[-1]}")
    cfg.dry_run = True
    uninstall(cfg, purge=True)
    cfg.dry_run = False
    with pytest.raises(PermissionError, match="cannot delete"):
        uninstall(cfg, purge=True)
    assert path.exists() or path.is_symlink()


def test_man_page_removal_propagates_deletion_failure(tmp_path, monkeypatch):
    cfg = graphviz.Config(
        tmp_path / "install", tmp_path / "cache", tmp_path / "bin", tmp_path / "man"
    )
    section = cfg.man_dir / "man1"
    section.mkdir(parents=True)
    page = section / "dot.1"
    page.touch()

    def fail(*args, **kwargs):
        raise PermissionError("cannot delete")

    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(PermissionError, match="cannot delete"):
        graphviz.remove_man_page_symlinks(cfg)
    assert page.exists()
