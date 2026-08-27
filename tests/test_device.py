# tests/test_device.py
import os

import pytest
from pathlib import Path
from y1sync.device import (
    BACKUP_RETENTION, Y1_SIGNATURE, looks_like_y1, find_devices,
    backup_device, safe_copy,
)


@pytest.fixture
def fake_y1(tmp_path):
    """A directory carrying the Y1 folder signature."""
    root = tmp_path / "Y1"
    for folder in Y1_SIGNATURE:
        (root / folder).mkdir(parents=True)
    (root / "Music" / "song.mp3").write_bytes(b"audio")
    return root


class FakePartition:
    def __init__(self, mountpoint, fstype="vfat"):
        self.mountpoint = str(mountpoint)
        self.fstype = fstype
        self.device = "/dev/fake"
        self.opts = "rw"


def test_recognises_the_folder_signature(fake_y1):
    assert looks_like_y1(fake_y1) is True


def test_rejects_an_unrelated_directory(tmp_path):
    (tmp_path / "Documents").mkdir()
    assert looks_like_y1(tmp_path) is False


def test_rejects_a_partial_signature(tmp_path):
    # A USB stick that happens to contain Music/ is not a Y1.
    (tmp_path / "Music").mkdir()
    assert looks_like_y1(tmp_path) is False


def test_rejects_a_missing_path(tmp_path):
    assert looks_like_y1(tmp_path / "nope") is False


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_rejects_a_directory_it_cannot_read(tmp_path):
    # A FAT volume the user cannot read (e.g. a root-owned /boot/efi on
    # Linux) must be reported as "not a Y1", not crash the scan.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o000)
    try:
        assert looks_like_y1(blocked) is False
    finally:
        blocked.chmod(0o755)


def test_finds_a_matching_partition(fake_y1):
    found = find_devices([FakePartition(fake_y1)])
    assert found == [fake_y1]


def test_ignores_non_fat_filesystems(fake_y1):
    # An ext4 volume with these folders is somebody's hard drive.
    assert find_devices([FakePartition(fake_y1, fstype="ext4")]) == []


def test_accepts_fat32_under_any_platform_name(fake_y1):
    for fstype in ("vfat", "msdos", "FAT32", "fat32"):
        assert find_devices([FakePartition(fake_y1, fstype=fstype)]) == [fake_y1]


def test_backup_copies_music_and_themes(fake_y1, tmp_path):
    (fake_y1 / "Themes" / "theme.png").write_bytes(b"png")
    destination = backup_device(fake_y1, tmp_path / "backups")
    assert (destination / "Music" / "song.mp3").read_bytes() == b"audio"
    assert (destination / "Themes" / "theme.png").read_bytes() == b"png"


def test_backup_never_writes_to_the_device(fake_y1, tmp_path):
    before = sorted(p.name for p in fake_y1.iterdir())
    backup_device(fake_y1, tmp_path / "backups")
    assert sorted(p.name for p in fake_y1.iterdir()) == before


def test_backup_refuses_a_destination_inside_the_device(fake_y1):
    # A backup destination under the device tree would write the backup
    # onto the very thing being backed up.
    before = sorted(p.name for p in fake_y1.iterdir())
    with pytest.raises(ValueError):
        backup_device(fake_y1, fake_y1 / "backup_on_device")
    assert sorted(p.name for p in fake_y1.iterdir()) == before


def test_backup_prunes_older_backups(fake_y1, tmp_path):
    # Each backup can be gigabytes and a sync runs often, so unbounded
    # retention quietly fills the user's home partition.
    root = tmp_path / "backups"
    stale = root / fake_y1.name
    stale.mkdir(parents=True)
    for stamp in ("2020-01-01_000000", "2021-01-01_000000", "2022-01-01_000000"):
        (stale / stamp).mkdir()

    backup_device(fake_y1, root, keep=2)

    kept = sorted(p.name for p in stale.iterdir())
    assert len(kept) == 2
    # Lexical order is chronological order for this stamp format, so the
    # survivors must be the newest, never the oldest.
    assert "2020-01-01_000000" not in kept
    assert "2021-01-01_000000" not in kept


def test_backup_keeps_the_most_recent_backups(fake_y1, tmp_path):
    root = tmp_path / "backups"
    destinations = []
    for stamp in ("2020-01-01_000000", "2021-01-01_000000"):
        older = root / fake_y1.name / stamp
        older.mkdir(parents=True)
        destinations.append(older)

    fresh = backup_device(fake_y1, root, keep=2)

    assert fresh.is_dir()
    assert (fresh / "Music" / "song.mp3").read_bytes() == b"audio"
    # The newest pre-existing backup survives alongside the one just made.
    assert destinations[1].is_dir()


def test_backup_retention_default_is_bounded():
    # A default of zero or None would restore the unbounded behaviour
    # this pruning exists to prevent.
    assert isinstance(BACKUP_RETENTION, int)
    assert BACKUP_RETENTION >= 1


def test_safe_copy_writes_the_file(tmp_path):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"payload")
    dst = tmp_path / "out" / "dst.mp3"
    safe_copy(src, dst)
    assert dst.read_bytes() == b"payload"


def test_safe_copy_leaves_no_temporary_file(tmp_path):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"payload")
    dst = tmp_path / "dst.mp3"
    safe_copy(src, dst)
    assert [p.name for p in tmp_path.iterdir()] == ["src.mp3", "dst.mp3"]


def test_safe_copy_overwrites_atomically(tmp_path):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"new")
    dst = tmp_path / "dst.mp3"
    dst.write_bytes(b"old")
    safe_copy(src, dst)
    assert dst.read_bytes() == b"new"


def test_safe_copy_cleans_up_the_temp_file_after_a_failed_copy(tmp_path, monkeypatch):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"new")
    dst = tmp_path / "dst.mp3"
    dst.write_bytes(b"old")

    def broken_fsync(fd):
        raise OSError("simulated interruption")

    monkeypatch.setattr(os, "fsync", broken_fsync)

    with pytest.raises(OSError):
        safe_copy(src, dst)

    assert dst.read_bytes() == b"old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dst.mp3", "src.mp3"]
