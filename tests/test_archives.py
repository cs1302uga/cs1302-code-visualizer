"""Archive extraction rejects traversal, special files, and escaping links."""

import stat
import tarfile
from io import BytesIO
from zipfile import ZipFile, ZipInfo

import pytest

from cs1302_code_visualizer.util.archives import archive_path, extract_zip


def zip_data(entries):
    """Create an in-memory archive from named payloads and Unix modes."""
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        for name, payload, mode in entries:
            member = ZipInfo(name)
            member.create_system = 3
            member.external_attr = mode << 16
            archive.writestr(member, payload)
    data.seek(0)
    return ZipFile(data)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:\\escape", "a/../../bad", "", "."])
def test_unsafe_archive_path(tmp_path, name):
    with pytest.raises(ValueError, match="Unsafe archive path"):
        archive_path(tmp_path, name)


def test_existing_symlink_cannot_redirect_extraction(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    with (
        zip_data([("link/escape", b"bad", 0)]) as archive,
        pytest.raises(ValueError, match="escapes"),
    ):
        extract_zip(archive, root)
    assert not (tmp_path / "escape").exists()


def test_zip_files_modes_and_internal_link(tmp_path):
    root = tmp_path / "root"
    entries = [
        ("bin/", b"", stat.S_IFDIR | 0o755),
        ("bin/java", b"java", stat.S_IFREG | 0o4755),
        ("bin/javac", b"java", stat.S_IFLNK | 0o777),
        ("LICENSE", b"license", 0),
    ]
    with zip_data(entries) as archive:
        extract_zip(archive, root)
    assert (root / "bin/java").read_bytes() == b"java"
    assert (root / "bin/java").stat().st_mode & 0o7777 == 0o755
    assert (root / "bin/javac").is_symlink()
    assert (root / "bin/javac").read_bytes() == b"java"
    assert (root / "LICENSE").read_bytes() == b"license"


@pytest.mark.parametrize("target", ["../../escape", "/absolute"])
def test_escaping_zip_symlink_is_rejected(tmp_path, target):
    with (
        zip_data([("link", target.encode(), stat.S_IFLNK | 0o777)]) as archive,
        pytest.raises(ValueError, match="symlink escapes"),
    ):
        extract_zip(archive, tmp_path / "root")
    assert not (tmp_path / "root/link").is_symlink()


def test_tar_data_filter_rejects_external_link(tmp_path):
    data = BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../escape"
        archive.addfile(link)
    data.seek(0)
    with tarfile.open(fileobj=data) as archive, pytest.raises(tarfile.LinkOutsideDestinationError):
        archive.extractall(tmp_path / "root", filter="data")


@pytest.mark.parametrize("platform_name", ["Linux", "Darwin"])
def test_jdk_download_does_not_ignore_tar_filter_errors(tmp_path, monkeypatch, platform_name):
    from unittest.mock import MagicMock

    from cs1302_code_visualizer import trace_generator

    payload = BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        link = tarfile.TarInfo("jdk/bin/java")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../../outside"
        archive.addfile(link)
    response = MagicMock()
    response.json.return_value = {"most_recent_lts": 25}
    response.iter_content.return_value = [payload.getvalue()]
    monkeypatch.setattr(trace_generator, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace_generator, "JDK_CACHE_DIR", tmp_path / "jdk")
    monkeypatch.setattr(trace_generator.platform, "system", lambda: platform_name)
    monkeypatch.setattr(trace_generator.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(trace_generator.requests, "get", lambda *args, **kwargs: response)
    with pytest.raises(tarfile.LinkOutsideDestinationError):
        trace_generator.download_jdk()
    assert not (tmp_path / "jdk/bin/java").is_symlink()
