# src/y1sync/device.py
"""Finding the Y1 and writing to it without destroying anything.

This is the only module that writes to removable media, and the only one
whose behaviour varies by operating system. Device *recognition* is
portable: it matches the Y1's folder layout rather than any path, so the
same code runs on Linux, macOS and Windows.
"""

import filecmp
import os
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import psutil

# The folder layout an Innioasis Y1 ships with. All four must be present:
# a USB stick that merely contains Music/ is not a Y1.
Y1_SIGNATURE = ("Music", "Themes", "Audiobooks", "Videos")

# What FAT32 is called by psutil across the three platforms.
FAT_FILESYSTEMS = {"vfat", "msdos", "fat", "fat32", "exfat"}

BACKUP_FOLDERS = ("Music", "Themes")

# How many timestamped backups to keep per device. A sync is run often
# (the expected usage is repeated runs on a growing folder), and each
# backup can be gigabytes, so backing up on every run without pruning
# quietly fills the home partition. Three keeps enough history to recover
# from a bad sync a couple of runs back while bounding worst-case backup
# storage to roughly three times one device's Music+Themes size.
BACKUP_RETENTION = 3


def looks_like_y1(path: Path) -> bool:
    """True when every folder in the Y1 signature is present.

    Any volume this process cannot inspect (permission denied, a stale
    mount, or any other OS-level failure) is definitively not a usable
    Y1, so it is treated as a plain False rather than letting the error
    propagate. This matters on ordinary Linux desktops: an unrelated FAT
    volume like /boot/efi can be root-owned, and find_devices() must be
    able to walk past it without crashing.
    """
    path = Path(path)
    try:
        if not path.is_dir():
            return False
        return all((path / folder).is_dir() for folder in Y1_SIGNATURE)
    except (PermissionError, OSError):
        return False


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


def _prune_old_backups(backups_dir: Path, keep: int) -> None:
    """Delete all but the `keep` most recent timestamped backups.

    Backup folders are named with a sortable "%Y-%m-%d_%H%M%S" stamp, so
    lexical order is chronological order.
    """
    if keep < 0:
        return
    stamps = sorted((p for p in backups_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    for stale in stamps[:-keep] if keep else stamps:
        shutil.rmtree(stale, ignore_errors=True)


def backup_device(device: Path, dest_root: Path, keep: int = BACKUP_RETENTION) -> Path:
    """Copy the device's music and themes to a timestamped local folder.

    Backups go to local storage, never to the device: the device may be
    full, failing, or the very thing being repaired. Only the `keep` most
    recent backups for this device are retained; older ones are pruned
    after the new backup completes so storage does not grow without bound
    across repeated syncs.
    """
    device = Path(device).resolve()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backups_dir = Path(dest_root) / device.name
    destination = backups_dir / stamp

    # Resolve before comparing so a relative path, a ".." segment or a
    # symlink cannot slip a destination inside the device tree past this
    # check. Writing the backup onto the device being backed up would
    # silently corrupt the very thing it is meant to protect.
    resolved_destination = destination.resolve()
    if resolved_destination == device or device in resolved_destination.parents:
        raise ValueError(
            f"backup destination {resolved_destination} is inside the "
            f"device tree {device}; refusing to write the backup onto "
            f"the device it is backing up"
        )

    # A full-device backup can take minutes; print before starting so a
    # long silent copy does not read as a hang.
    print(f"Backing up {device.name} to {destination} ...")

    destination.mkdir(parents=True, exist_ok=True)
    for folder in BACKUP_FOLDERS:
        source = device / folder
        if source.is_dir():
            shutil.copytree(source, destination / folder, dirs_exist_ok=True)

    _prune_old_backups(backups_dir, keep)
    return destination


# FAT32 stores mtimes with 2-second resolution, so comparing exactly
# would treat every file a previous sync already copied as changed again.
_MTIME_TOLERANCE = 2.0


def copy_status(src: Path, dst: Path) -> str:
    """How dst on the device compares to src in the library.

    - "absent"      -- dst is missing; it has to be copied.
    - "differs"     -- dst holds different bytes than src; it has to be recopied.
    - "stale-mtime" -- dst already holds exactly src's bytes, but its timestamp
                       has drifted past FAT's 2s resolution. yt2mp3 re-tagging
                       rewrites a file in place without changing its length, so
                       this is the usual aftermath of a re-tag: nothing needs to
                       cross USB, only dst's mtime wants restamping so the next
                       run's cheap size+mtime check passes.
    - "current"     -- dst matches src; nothing to do.

    A sync is run often on a library that mostly hasn't changed, and
    re-sending gigabytes of already-identical audio over USB on every run is
    the difference between a sync that takes seconds and one that takes
    minutes. The steady-state case -- sizes and mtimes agree -- still costs
    only a stat per side and never opens a file. Bytes are compared only when
    the sizes match but the mtimes disagree, i.e. exactly the files a re-tag
    left looking changed when their audio is untouched; an earlier version
    recopied every one of them.
    """
    try:
        dst_stat = dst.stat()
    except OSError:
        return "absent"
    src_stat = src.stat()
    if dst_stat.st_size != src_stat.st_size:
        return "differs"
    if abs(dst_stat.st_mtime - src_stat.st_mtime) <= _MTIME_TOLERANCE:
        return "current"
    return "stale-mtime" if filecmp.cmp(src, dst, shallow=False) else "differs"


def needs_copy(src: Path, dst: Path) -> bool:
    """True when dst is missing or holds different bytes than src.

    A metadata-only timestamp drift (copy_status's "stale-mtime") is
    deliberately not a reason to copy -- re-sending an identical file over
    USB is the exact cost this check exists to avoid. cmd_sync restamps
    those separately so the drift does not outlive one run.
    """
    return copy_status(src, dst) in ("absent", "differs")


def restamp(src: Path, dst: Path) -> None:
    """Set dst's mtime to src's without touching its bytes.

    The device already holds src's exact contents -- copy_status returned
    "stale-mtime" -- and only the timestamp drifted. Mirroring it back, the
    same thing safe_copy does after a real copy, lets the next run's cheap
    size+mtime check skip the file instead of reading both sides again. A
    directory-entry write, not a data write: if it does not land, the next
    run simply compares bytes once more.
    """
    src_stat = Path(src).stat()
    os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))


def needs_transcode(src: Path, dst: Path) -> bool:
    """True when dst, a converted file, is missing or older than src.

    Unlike needs_copy, dst is not a byte-for-byte copy of src, so size
    tells us nothing -- only presence and mtime can say whether an
    earlier sync already produced it. wav_to_flac() mirrors src's mtime
    onto dst once the conversion lands, exactly as safe_copy() does for a
    plain copy, which is what makes this comparison hold across runs.
    """
    try:
        dst_stat = dst.stat()
    except OSError:
        return True
    return abs(dst_stat.st_mtime - src.stat().st_mtime) > _MTIME_TOLERANCE


def safe_copy(src: Path, dst: Path) -> None:
    """Copy src to dst so an interruption cannot corrupt dst.

    The bytes land in a temporary file and are flushed to the physical
    device before the rename makes them visible. A power loss mid-copy
    leaves the previous file intact rather than a truncated one.
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(f".y1sync-{dst.name}.part")

    expected_size = src.stat().st_size

    try:
        with open(src, "rb") as reader, open(temp, "wb") as writer:
            shutil.copyfileobj(reader, writer)
            writer.flush()
            # fsync, not os.sync: os.sync does not exist on Windows, and this
            # guarantees the specific file rather than something global.
            os.fsync(writer.fileno())
        # Found on a real Y1, on a plugged-in device with nothing unplugged
        # mid-copy: fsync above returned, and the copy still landed as an
        # empty file. Whether that's a flaky USB controller lying about a
        # completed write or something else, the fix is the same either
        # way -- check, rather than trust, that the bytes actually arrived.
        written = temp.stat().st_size
        if written != expected_size:
            raise OSError(
                f"wrote {written} bytes to {dst.name}, expected {expected_size} "
                "-- the copy did not fully land"
            )
    except BaseException:
        # An interrupted or short copy must not leave a stray .part file
        # behind, and the destination's existing bytes must be untouched
        # since the rename below never happens.
        temp.unlink(missing_ok=True)
        raise

    os.replace(temp, dst)

    # The rename above is a separate write to the parent directory from the
    # data written above, on FAT filesystems in particular, and the size
    # actually visible under dst's final name is what a corrupted copy
    # would show up as. Checked here rather than assumed from temp's size
    # a moment ago: the exact bug this guards is the destination coming out
    # different from what was just verified.
    copied_size = dst.stat().st_size
    if copied_size != expected_size:
        # Leaving the short file in place is worse than removing it: the Y1
        # shows a 0-byte track as a "broken file" and the next sync, seeing
        # a size mismatch, just tries the copy again. Deleting it means the
        # track is plainly missing -- which the FAILED line above already
        # says -- instead of silently unplayable.
        dst.unlink(missing_ok=True)
        raise OSError(
            f"{dst.name} is {copied_size} bytes right after copying, "
            f"expected {expected_size} -- the write did not fully land"
        )

    # Mirrors src's mtime onto dst rather than leaving the copy's own
    # timestamp, so a later sync can tell an already-copied file apart
    # from a changed one by size and mtime alone -- see needs_copy()
    # below -- without re-reading every file's contents on each run.
    src_stat = src.stat()
    os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))

    # fsync above only guarantees the temp file's bytes; the rename that
    # makes them visible under dst's name is a separate write to the
    # parent directory, and that one was never flushed. Found on a real
    # Y1: unplugging right after "safe to disconnect" left a file present
    # at the right name with the right entry, but 0 bytes -- the rename
    # had not reached the medium yet. Not supported on Windows, where a
    # directory cannot be opened like this; the copy already succeeded,
    # so a failure here only loses this extra guarantee, not the data.
    try:
        dir_fd = os.open(dst.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def _block_device_for(mount: Path) -> str | None:
    """The /dev node backing `mount`, or None if it can't be determined."""
    try:
        for part in psutil.disk_partitions(all=False):
            if Path(part.mountpoint) == Path(mount):
                return part.device
    except OSError:
        pass
    return None


def flush_and_eject(mount: Path) -> bool:
    """Flush every pending write to the medium, then unmount `mount`.

    fsync-ing each copied file is not enough on FAT: the allocation table
    that chains a file's clusters together is written lazily, so a track
    that copied cleanly still reads back as 0 bytes -- the Y1's "broken
    file" -- if the device is unplugged before that table lands. os.sync()
    forces it out on POSIX; the unmount then makes "safe to disconnect"
    actually true.

    Returns True only if the volume was unmounted. The unmount is
    best-effort -- no udisks, a volume still busy, or Windows (which has
    no scriptable eject) all just return False, and the caller falls back
    to telling the user to eject it by hand.
    """
    if hasattr(os, "sync"):
        os.sync()

    system = platform.system()
    if system == "Windows":
        return False

    mount = Path(mount)
    if system == "Darwin":
        attempts = [["diskutil", "unmount", str(mount)]]
    else:
        attempts = []
        dev = _block_device_for(mount)
        if dev:
            attempts.append(["udisksctl", "unmount", "-b", dev])
        attempts.append(["umount", str(mount)])
        attempts.append(["eject", str(mount)])

    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return True
    return False
