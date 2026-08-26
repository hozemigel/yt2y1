"""Command-line entry point for y1sync."""

import argparse
import shutil
import sys
from pathlib import Path

from .artwork import artwork_url_for, fetch_artwork
from .cache import ContentCache
from .config import load_config
from .device import backup_device, find_devices, safe_copy
from .identify import identify
from .naming import rename_file, resolve_collision, safe_filename
from .ranking import decide
from .review import choose_candidate
from .tagging import write_tags

CACHE_ROOT = Path.home() / ".cache" / "y1sync"
BACKUP_ROOT = Path.home() / ".local" / "share" / "y1sync" / "backups"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="y1sync",
        description="Prepare and sync music libraries for the Innioasis Y1.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="Report dependencies and device status")

    for name, help_text in (
        ("scan", "Identify, tag and rename MP3s in a folder"),
        ("sync", "Copy a prepared folder to the device"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("folder", help="Folder containing MP3 files")
        sub.add_argument("--dry-run", action="store_true",
                         help="Report what would change; write nothing")
        sub.add_argument("--yes", action="store_true",
                         help="Accept the top-ranked candidate without prompting")
        sub.add_argument("--verbose", action="store_true",
                         help="Show per-track detail including confidence scores")

    return parser


def cmd_doctor() -> int:
    config = load_config()
    print("y1sync environment check\n")
    for tool, purpose in (("ffmpeg", "audio decoding"),
                          ("fpcalc", "audio fingerprinting (chromaprint)")):
        found = shutil.which(tool)
        status = found if found else "NOT FOUND"
        print(f"  {tool:8} {status}   ({purpose})")

    key_status = "configured" if config.acoustid_key else "NOT CONFIGURED"
    print(f"  {'API key':8} {key_status}   (AcoustID)")

    if not config.acoustid_key or not shutil.which("fpcalc"):
        print("\nWithout chromaprint and an AcoustID key, tracks are identified")
        print("from their filenames alone and every one needs manual review.")
        print("Install chromaprint and get a free key at https://acoustid.org/")

    devices = find_devices()
    print(f"\n  Devices  {devices[0] if devices else 'no Innioasis Y1 found'}")
    return 0


def cmd_scan(folder: str, dry_run: bool, yes: bool, verbose: bool) -> int:
    root = Path(folder)
    if not root.is_dir():
        print(f"Not a folder: {root}")
        return 1

    files = sorted(p for p in root.iterdir() if p.suffix.lower() == ".mp3")
    if not files:
        print(f"No MP3 files in {root}")
        return 0

    config = load_config()
    cache = ContentCache(CACHE_ROOT / "identify")
    auto_accepted: list[str] = []
    taken: set[str] = set()

    for path in files:
        candidates = cache.get(path)
        if candidates is None:
            candidates = identify(path, config.acoustid_key)
            cache.put(path, candidates)

        pick, needs_review = decide(candidates)
        if needs_review and not yes:
            pick = choose_candidate(path, candidates)
        elif needs_review and pick is not None:
            auto_accepted.append(f"{path.name} -> {pick.meta.album}")

        if pick is None:
            print(f"  skipped  {path.name}")
            continue

        new_name = resolve_collision(safe_filename(pick.meta), taken)
        taken.add(new_name)

        if verbose:
            print(f"  {path.name}\n      -> {new_name}  (confidence {pick.confidence:.2f})")

        if dry_run:
            print(f"  would tag and rename  {path.name} -> {new_name}")
            continue

        # AcoustID candidates carry no artwork URL; look one up.
        art_url = pick.artwork_url or artwork_url_for(pick.meta)
        artwork = fetch_artwork(art_url, CACHE_ROOT / "artwork")
        write_tags(path, pick.meta, artwork)
        rename_file(path, new_name)
        print(f"  tagged   {new_name}")

    if auto_accepted:
        print("\nAuto-accepted ambiguous tracks (--yes):")
        for line in auto_accepted:
            print(f"  {line}")
    return 0


def cmd_sync(folder: str, dry_run: bool, verbose: bool) -> int:
    source = Path(folder)
    if not source.is_dir():
        print(f"Not a folder: {source}")
        return 1

    devices = find_devices()
    if not devices:
        print("No Innioasis Y1 found. Connect the device and try again.")
        return 1

    device = devices[0]
    files = sorted(p for p in source.iterdir() if p.suffix.lower() == ".mp3")
    print(f"Device: {device}")

    if dry_run:
        for path in files:
            print(f"  would copy  {path.name}")
        return 0

    backup = backup_device(device, BACKUP_ROOT)
    print(f"Backup: {backup}")

    for path in files:
        safe_copy(path, device / "Music" / path.name)
        if verbose:
            print(f"  copied   {path.name}")

    print(f"Copied {len(files)} file(s). Safe to disconnect.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "scan":
        return cmd_scan(args.folder, args.dry_run, args.yes, args.verbose)
    if args.command == "sync":
        return cmd_sync(args.folder, args.dry_run, args.verbose)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
