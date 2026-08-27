"""Command-line entry point for y1sync."""

import argparse
import shutil
import sys
from pathlib import Path

from .artwork import artwork_url_for, fetch_artwork
from .cache import ContentCache
from .config import load_config
from .device import backup_device, find_devices, safe_copy
from .identify import AcoustIDKeyRejected, identify
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

    # Identifications and the answers to review questions are remembered
    # here, so a wrong answer stays wrong until this is deleted.
    print(f"\n  Cache    {CACHE_ROOT}")
    print("           Delete it to re-identify tracks and be asked again.")

    if not config.acoustid_key or not shutil.which("fpcalc"):
        print("\nWithout chromaprint and an AcoustID key, tracks are identified")
        print("from their filenames alone and every one needs manual review.")
        print("Install chromaprint and get a free key at https://acoustid.org/")

    devices = find_devices()
    print(f"\n  Devices  {devices[0] if devices else 'no Innioasis Y1 found'}")
    return 0


def _existing_names(directory: Path) -> set[str]:
    """Every name already present in a directory, MP3 or not."""
    try:
        return {entry.name for entry in directory.iterdir()}
    except OSError:
        return set()


def _is_a_guess(candidate) -> bool:
    """True when nothing but the filename supports this identification."""
    return candidate is not None and candidate.source != "acoustid"


def _find_mp3s(root: Path) -> list[Path]:
    """Every MP3 under root, at any depth, sorted for stable output.

    A library organised into artist/album folders is the normal case, not
    an edge case: iterdir() alone would miss almost everything a real
    music collection contains.
    """
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".mp3")


def cmd_scan(folder: str, dry_run: bool, yes: bool, verbose: bool) -> int:
    root = Path(folder)
    if not root.is_dir():
        print(f"Not a folder: {root}")
        return 1

    files = _find_mp3s(root)
    if not files:
        print(f"No MP3 files in {root}")
        return 0

    config = load_config()
    cache = ContentCache(CACHE_ROOT / "identify")
    auto_accepted: list[str] = []
    unconfirmed: list[str] = []
    # Names already in use, per directory. Seeded from what is on disk, not
    # from an empty set: the folder usually already holds files this tool
    # named on an earlier run, and a name it does not know about is a name
    # it would happily rename over. Keyed by parent directory, so two
    # subfolders that both produce "Artist - Title.mp3" never collide with
    # each other: only files sharing an actual folder compete for a name.
    taken: dict[Path, set[str]] = {}
    failures = 0
    previewed = 0

    for path in files:
        try:
            entry = cache.get(path)
            if entry is None:
                candidates = identify(path, config.acoustid_key)
                pick = None
            else:
                candidates, pick = entry.candidates, entry.choice

            if pick is None:
                pick, needs_review = decide(candidates)
                if needs_review and yes and _is_a_guess(pick):
                    # --yes exists to skip choosing between plausible
                    # releases of a known recording. A filename guess is a
                    # different thing: nothing has confirmed the audio is
                    # even this track, and accepting it unseen reproduces
                    # the misidentification this tool exists to prevent.
                    unconfirmed.append(f"{path.name} -> {pick.meta.artist} - {pick.meta.title}")
                    print(f"  needs review  {path.name} (identified from its filename)")
                    continue
                if needs_review and not yes:
                    pick = choose_candidate(path, candidates)
                elif needs_review and pick is not None:
                    auto_accepted.append(f"{path.name} -> {pick.meta.album}")

            if pick is None:
                # A skip is not recorded: the user may be waiting on
                # chromaprint or a better answer, and a remembered skip
                # would hide the track from every future run.
                print(f"  skipped  {path.name}")
                continue

            if not dry_run:
                # Recorded before tagging, so an interruption later does not
                # cost the user the answer they just gave. The key is the
                # audio payload, which tagging does not change.
                cache.put(path, candidates, choice=pick)

            names = taken.setdefault(path.parent, _existing_names(path.parent))
            # A file must not be blocked from keeping the name it already
            # has, so re-scanning a tidy folder is a no-op rather than a
            # cascade of " (2)" suffixes. The comparison is case-insensitive
            # because FAT32 is.
            others = {n for n in names if n.lower() != path.name.lower()}
            new_name = resolve_collision(safe_filename(pick.meta), others)
            names.add(new_name)

            if verbose:
                print(f"  {path.name}\n      -> {new_name}  (confidence {pick.confidence:.2f})")

            if dry_run:
                rel = path.relative_to(root)
                print(f"  would tag and rename  {rel} -> {new_name}")
                previewed += 1
                continue

            # AcoustID candidates carry no artwork URL; look one up.
            art_url = pick.artwork_url or artwork_url_for(pick.meta)
            artwork = fetch_artwork(art_url, CACHE_ROOT / "artwork")
            write_tags(path, pick.meta, artwork)
            rename_file(path, new_name)
            print(f"  tagged   {new_name}")
        except AcoustIDKeyRejected as exc:
            # A bad key is a property of the run, not of this file: every
            # remaining track would fail identically, and finishing the
            # library on filename guesses is exactly what this tool exists
            # to prevent. Stop and say so once.
            print(f"\n{exc}")
            return 1
        except Exception as exc:
            failures += 1
            print(f"  FAILED   {path.name}: {exc}")

    if dry_run:
        print(f"\n{previewed} file(s) would be tagged and renamed.")

    if auto_accepted:
        print("\nAuto-accepted ambiguous tracks (--yes):")
        for line in auto_accepted:
            print(f"  {line}")

    if unconfirmed:
        print(f"\n{len(unconfirmed)} track(s) left untagged: identified only from")
        print("their filenames, which --yes will not accept unseen.")
        for line in unconfirmed:
            print(f"  {line}")
        print("\nRun without --yes to review them, or set up fingerprinting")
        print("(y1sync doctor) so they can be identified from the audio.")

    if failures:
        print(f"\n{failures} file(s) failed.")
        if failures == len(files):
            return 1
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
    files = _find_mp3s(source)
    print(f"Device: {device}")

    if dry_run:
        for path in files:
            print(f"  would copy  {path.relative_to(source)}")
        print(f"\n{len(files)} file(s) would be copied.")
        return 0

    backup = backup_device(device, BACKUP_ROOT)
    print(f"Backup: {backup}")

    failures = 0
    for path in files:
        # The tree found under the source folder is preserved on the
        # device rather than flattened: two files both called "rip.mp3"
        # in different album folders must not collide in Music/.
        rel = path.relative_to(source)
        try:
            safe_copy(path, device / "Music" / rel)
            if verbose:
                print(f"  copied   {rel}")
        except Exception as exc:
            failures += 1
            print(f"  FAILED   {rel}: {exc}")

    print(f"Copied {len(files) - failures} file(s). Safe to disconnect.")
    if failures:
        print(f"{failures} file(s) failed.")
        if failures == len(files):
            return 1
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
