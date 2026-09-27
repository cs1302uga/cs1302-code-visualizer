"""Extract downloaded ZIP files without allowing paths or links to escape."""

import shutil
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def archive_path(root: Path, name: str) -> Path:
    """Resolve an archive-relative path, rejecting absolute paths and traversal."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in name or not path.parts:
        raise ValueError(f"Unsafe archive path: {name!r}")
    destination = root.joinpath(*path.parts)
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Archive path escapes extraction directory: {name!r}")
    return destination


def extract_zip(archive: ZipFile, root: Path) -> None:
    """Extract files and internal symlinks, checking each path before writing."""
    root.mkdir(parents=True, exist_ok=True)
    for member in archive.infolist():
        destination = archive_path(root, member.filename)
        mode = member.external_attr >> 16
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISLNK(mode):
            target = archive.read(member).decode("utf-8")
            if not (destination.parent / target).resolve().is_relative_to(root.resolve()):
                raise ValueError(f"Archive symlink escapes extraction directory: {target!r}")
            destination.symlink_to(target)
        else:
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            if mode & 0o777:
                destination.chmod(mode & 0o777)
