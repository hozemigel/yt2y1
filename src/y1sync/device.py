# src/y1sync/device.py
"""Finding the Y1 and writing to it without destroying anything.

This is the only module that writes to removable media, and the only one
whose behaviour varies by operating system. Device *recognition* is
portable: it matches the Y1's folder layout rather than any path, so the
same code runs on Linux, macOS and Windows.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

import psutil

# The folder layout an Innioasis Y1 ships with. All four must be present:
# a USB stick that merely contains Music/ is not a Y1.
Y1_SIGNATURE = ("Music", "Themes", "Audiobooks", "Videos")

# What FAT32 is called by psutil across the three platforms.
FAT_FILESYSTEMS = {"vfat", "msdos", "fat", "fat32", "exfat"}

BACKUP_FOLDERS = ("Music", "Themes")


def looks_like_y1(path: Path) -> bool:
    """True when every folder in the Y1 signature is present."""
    path = Path(path)
    if not path.is_dir():
        return False
    return all((path / folder).is_dir() for folder in Y1_SIGNATURE)


def find_devices(partitions=None) -> list[Path]:
    """Return mounted volumes that look like a Y1.

    psutil.disk_partitions() covers Linux mount points, macOS /Volumes
    entries and Windows drive letters uniformly, so no per-OS branching
    is needed here.
    """
    if partitions is None:
        partitions = psutil.disk_partitions(all=False)
    found = []
    for part in partitions:
        if part.fstype.lower() not in FAT_FILESYSTEMS:
            continue
        mount = Path(part.mountpoint)
        if looks_like_y1(mount):
            found.append(mount)
    return found


def backup_device(device: Path, dest_root: Path) -> Path:
    """Copy the device's music and themes to a timestamped local folder.

    Backups go to local storage, never to the device: the device may be
    full, failing, or the very thing being repaired.
    """
    device = Path(device)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destination = Path(dest_root) / device.name / stamp
    destination.mkdir(parents=True, exist_ok=True)
    for folder in BACKUP_FOLDERS:
        source = device / folder
        if source.is_dir():
            shutil.copytree(source, destination / folder, dirs_exist_ok=True)
    return destination


def safe_copy(src: Path, dst: Path) -> None:
    """Copy src to dst so an interruption cannot corrupt dst.

    The bytes land in a temporary file and are flushed to the physical
    device before the rename makes them visible. A power loss mid-copy
    leaves the previous file intact rather than a truncated one.
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(f".y1sync-{dst.name}.part")

    with open(src, "rb") as reader, open(temp, "wb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        # fsync, not os.sync: os.sync does not exist on Windows, and this
        # guarantees the specific file rather than something global.
        os.fsync(writer.fileno())

    os.replace(temp, dst)
