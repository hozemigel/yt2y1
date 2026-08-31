"""Command-line entry point for y1sync."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError

from .artwork import artwork_url_for, fetch_artwork
from .cache import ContentCache
from .config import Config, load_config, save_config
from .device import (
    backup_device, copy_status, find_devices, needs_transcode, restamp, safe_copy,
)
from .formats import SUPPORTED_EXTENSIONS, device_target_name, find_audio
from .identify import AcoustIDKeyRejected, acoustid_key, identify
from .naming import rename_file, resolve_collision, safe_filename
from .ranking import decide, length_mismatch
from .review import choose_candidate
from .tagging import write_tags
from .transcode import wav_to_flac

CACHE_ROOT = Path.home() / ".cache" / "y1sync"
BACKUP_ROOT = Path.home() / ".local" / "share" / "y1sync" / "backups"

# Folders commonly used for downloaded or ripped music, checked first so
# an obvious folder always leads the discovered list even if a deeper,
# less relevant one would otherwise be found first.
_COMMON_MUSIC_FOLDER_NAMES = ("Music", "Downloads", "Desktop")

# Directories a music-folder search should not descend into: either
# irrelevant (hidden config folders) or large enough to turn a first-run
# prompt that should feel instant into a multi-second hang.
_SKIP_DIR_NAMES = {"node_modules", "__pycache__", "venv", ".venv", "Trash", "$RECYCLE.BIN"}
_MAX_SEARCH_DEPTH = 4
_MAX_DIRS_VISITED = 20000


def discover_music_folders(root: Path, limit: int = 6) -> list[Path]:
    """Find folders under root that directly contain music files.

    Runs before the user has done anything else, so it is bounded in both
    depth and total directories visited: on a home directory with years
    of accumulated files, an unbounded walk would not feel instant.
    """
    found: list[Path] = []
    visited = 0

    def scan(directory: Path, depth: int) -> None:
        nonlocal visited
        if len(found) >= limit or visited >= _MAX_DIRS_VISITED:
            return
        visited += 1
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        if any(e.is_file() and e.suffix.lower() in SUPPORTED_EXTENSIONS
               for e in entries):
            found.append(directory)
        if depth >= _MAX_SEARCH_DEPTH:
            return
        for entry in entries:
            if len(found) >= limit or visited >= _MAX_DIRS_VISITED:
                return
            if (entry.is_dir() and not entry.name.startswith(".")
                    and entry.name not in _SKIP_DIR_NAMES):
                scan(entry, depth + 1)

    for name in _COMMON_MUSIC_FOLDER_NAMES:
        candidate = root / name
        if candidate.is_dir():
            scan(candidate, 0)
    scan(root, 0)

    seen: set[Path] = set()
    unique = []
    for folder in found:
        if folder not in seen:
            seen.add(folder)
            unique.append(folder)
    return unique[:limit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="y1sync",
        description="Prepare and sync music libraries for the Innioasis Y1.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="Report dependencies and device status")

    scan = subparsers.add_parser("scan", help="Identify, tag and rename music files in a folder")
    scan.add_argument("folder", help="Folder containing music files")
    scan.add_argument("--dry-run", action="store_true",
                       help="Report what would change; write nothing")
    scan.add_argument("--yes", action="store_true",
                       help="Accept the top-ranked candidate without prompting")
    scan.add_argument("--verbose", action="store_true",
                       help="Show per-track detail including confidence scores")

    # No --yes: sync never asks a question to skip in the first place --
    # every file it decides to touch is copied outright, so accepting one
    # here would silently do nothing, which is worse than not offering it.
    sync = subparsers.add_parser("sync", help="Copy a prepared folder to the device")
    sync.add_argument("folder", help="Folder containing music files")
    sync.add_argument("--dry-run", action="store_true",
                       help="Report what would change; write nothing")
    sync.add_argument("--verbose", action="store_true",
                       help="Show per-track detail including confidence scores")

    return parser


def cmd_doctor() -> int:
    config = load_config()
    ffmpeg_found = shutil.which("ffmpeg")
    fpcalc_found = shutil.which("fpcalc")
    devices = find_devices()
    device = devices[0] if devices else None
    # yt-dlp now needs a JS runtime to extract YouTube reliably -- without
    # one it falls back to a slower, more failure-prone path (repeated
    # timeouts, truncated downloads). Not a hard prerequisite the way
    # ffmpeg/chromaprint are, since downloads work without it; left out of
    # `ready` below for the same reason the Y1 connection is.
    deno_found = shutil.which("deno")

    # (label, present, hint shown only when missing)
    #
    # The AcoustID key is no longer on this list: y1sync ships with one, so
    # fingerprinting needs only ffmpeg and chromaprint installed. A bad key
    # is now surfaced by scan itself, not pre-checked here.
    checks = [
        ("ffmpeg", bool(ffmpeg_found),
         "needed to decode audio -- see the README for install steps"),
        ("chromaprint", bool(fpcalc_found),
         "needed for accurate song matching -- see the README"),
        ("Y1 player", bool(device),
         "not connected"),
        ("JS runtime (deno)", bool(deno_found),
         "recommended for reliable YouTube downloads -- see the README"),
    ]

    print("Checking setup...\n")
    for label, present, hint in checks:
        mark = "✓" if present else "✗"
        print(f"  {mark} {label}" + (f"  ({hint})" if not present else ""))

    if config.acoustid_key:
        print("\n  AcoustID: using the key set in your config.")
    else:
        print("\n  AcoustID: using y1sync's built-in key -- nothing to set up.")

    print()
    # Whether the device happens to be plugged in right now doesn't affect
    # whether the software side is ready -- that's checked separately by
    # sync itself, and nagging about it here would read as an error on
    # every run before you've connected the player at all.
    ready = bool(ffmpeg_found) and bool(fpcalc_found)
    if ready and device:
        print(f"You're ready -- the Y1 is connected at {device}. "
              'Choose "Update player" from the menu.')
    elif ready:
        print('You\'re ready. Connect the Y1 over USB, then choose '
              '"Update player" from the menu.')
    else:
        first_missing = next(label for label, present, _ in checks[:2] if not present)
        print(f"Almost there -- fix {first_missing} above, then run this again.")

    # Identifications and the answers to review questions are remembered
    # here, so a wrong answer stays wrong until this is deleted. Kept out
    # of the checklist above: it's a troubleshooting detail, not part of
    # whether setup is ready.
    print("\n" + "-" * 40)
    print(f"Cache: {CACHE_ROOT}")
    print("(delete this folder to re-check songs already tagged)")
    return 0


# Where the installers clone the repo -- ~/yt2y1 on every platform, since
# Path.home() resolves to the right thing on Windows too. Checking for
# updates only works against this standard layout; a custom install
# elsewhere is told so rather than guessed at.
REPO_DIR = Path.home() / "yt2y1"


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    """Run a git command in cwd. None means git itself couldn't be run."""
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def cmd_check_for_updates(input_fn=input, output_fn=print) -> int:
    """Check the cloned repo for new commits, and offer to pull and reinstall.

    Assumes the standard layout the installers set up: yt2y1 cloned to
    REPO_DIR, running from whatever interpreter -- venv or system --
    y1sync happens to be installed into. Reinstalling uses sys.executable
    rather than assuming a venv exists, so the same "pip install
    --upgrade" lands correctly regardless of which installer was used.
    """
    if not (REPO_DIR / ".git").is_dir():
        output_fn(f"No git checkout found at {REPO_DIR}.")
        output_fn("Updates can only be checked for the standard install -- "
                   "re-run the installer from the README to get the latest version.")
        return 1

    output_fn("Checking for updates...")
    fetch = _run_git(["fetch", "--quiet"], REPO_DIR)
    if fetch is None or fetch.returncode != 0:
        output_fn("Could not check for updates -- are you online?")
        if fetch is not None and fetch.stderr.strip():
            output_fn(fetch.stderr.strip())
        return 1

    count = _run_git(["rev-list", "--count", "HEAD..@{u}"], REPO_DIR)
    if count is None or count.returncode != 0:
        output_fn("Could not compare against the remote -- this checkout may not be")
        output_fn("on a branch with an upstream set.")
        return 1

    behind = int(count.stdout.strip() or 0)
    if behind == 0:
        output_fn("Already up to date.")
        return 0

    plural = "commit" if behind == 1 else "commits"
    output_fn(f"\n{behind} new {plural} available:")
    log = _run_git(["log", "--oneline", "HEAD..@{u}"], REPO_DIR)
    if log is not None and log.stdout.strip():
        for line in log.stdout.splitlines():
            output_fn(f"  {line}")

    reply = _ask("\nUpdate now? [Y/n]: ", input_fn, output_fn).lower()
    if reply not in ("", "y", "yes"):
        output_fn("Not updating.")
        return 0

    output_fn("\nPulling the latest changes...")
    # --ff-only: a local checkout the installer manages should never have
    # its own commits to reconcile. If it does (someone modified it by
    # hand), failing loudly here beats a surprise merge.
    pull = _run_git(["pull", "--ff-only"], REPO_DIR)
    if pull is None or pull.returncode != 0:
        output_fn("git pull failed.")
        if pull is not None and pull.stderr.strip():
            output_fn(pull.stderr.strip())
        return 1

    output_fn("Reinstalling yt2mp3 and y1sync...")
    try:
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade",
             str(REPO_DIR / "yt2mp3"), str(REPO_DIR / "y1sync")],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.SubprocessError as exc:
        output_fn(f"Reinstall failed: {exc}")
        return 1
    if install.returncode != 0:
        output_fn("Reinstall failed.")
        if install.stderr.strip():
            output_fn(install.stderr.strip())
        return 1

    output_fn("\nUpdated. Restart y1sync to use the new version.")
    return 0


def _existing_names(directory: Path) -> set[str]:
    """Every name already present in a directory, audio or not."""
    try:
        return {entry.name for entry in directory.iterdir()}
    except OSError:
        return set()


def _is_a_guess(candidate) -> bool:
    """True when nothing but the filename supports this identification."""
    return candidate is not None and candidate.source != "acoustid"


def _audio_length(path: Path) -> float | None:
    """The file's playing time in seconds, or None if it can't be read.

    Fed to decide() so a fingerprint match against a recording of a very
    different length is sent to review rather than applied: an AcoustID
    fingerprint only covers the first ~120s, so a short edit can match the
    full-length original.
    """
    try:
        audio = MutagenFile(path)
    except (MutagenError, OSError, ValueError):
        return None
    if audio is None or audio.info is None:
        return None
    return getattr(audio.info, "length", None)


def cmd_scan(
    folder: str, dry_run: bool, yes: bool, verbose: bool, only: set[Path] | None = None
) -> int:
    """Identify, tag and rename the music files under folder.

    ``only``, when given, restricts the run to that subset of files rather
    than everything under folder -- used by cmd_download_and_sync so that
    downloading one track doesn't drag every other unresolved file in the
    music folder into review along with it. Left as None for the ``scan``
    subcommand and "Update player", where sweeping the whole folder is the
    point.
    """
    root = Path(folder)
    if not root.is_dir():
        print(f"Not a folder: {root}")
        return 1

    files = find_audio(root)
    if only is not None:
        # Resolved on both sides before comparing: `only`'s paths come from
        # yt-dlp's own report of what it wrote, which isn't guaranteed to
        # share the exact string form -- relative vs. absolute, "./"
        # segments -- of what rglob() finds below, even when they name the
        # same file.
        only_resolved = {path.resolve() for path in only}
        files = [path for path in files if path.resolve() in only_resolved]
    if not files:
        if only is None:
            print(f"No music files in {root}")
        return 0

    config = load_config()
    api_key = acoustid_key(config.acoustid_key)
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
                candidates = identify(path, api_key)
                pick = None
            else:
                candidates, pick = entry.candidates, entry.choice

            if pick is None:
                file_length = _audio_length(path)
                pick, needs_review = decide(candidates, file_duration=file_length)
                if needs_review and yes and _is_a_guess(pick):
                    # --yes exists to skip choosing between plausible
                    # releases of a known recording. A filename guess is a
                    # different thing: nothing has confirmed the audio is
                    # even this track, and accepting it unseen reproduces
                    # the misidentification this tool exists to prevent.
                    unconfirmed.append(f"{path.name} -> {pick.meta.artist} - {pick.meta.title}")
                    why = (
                        "identified from the YouTube page, not its audio"
                        if pick.source == "youtube"
                        else "identified from its filename"
                    )
                    print(f"  needs review  {path.name} ({why})")
                    continue
                if needs_review and yes and length_mismatch(pick, file_length):
                    # Same reasoning: a fingerprint match against a
                    # recording of a very different length has not
                    # confirmed this is that track, so --yes must not
                    # apply it unseen.
                    unconfirmed.append(f"{path.name} -> {pick.meta.artist} - {pick.meta.title}")
                    print(f"  needs review  {path.name} (its length doesn't match the match)")
                    continue
                if needs_review and not yes:
                    pick = choose_candidate(path, candidates, file_duration=file_length)
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
            new_name = resolve_collision(safe_filename(pick.meta, path.suffix), others)
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
        print(f"\n{len(unconfirmed)} track(s) left untagged: --yes will not accept")
        print("a filename guess or a length-mismatched match unseen.")
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
    files = find_audio(source)
    print(f"Device: {device}")

    # The tree found under the source folder is preserved on the device
    # rather than flattened: two files both called "rip.mp3" in different
    # album folders must not collide in Music/. A WAV maps to a FLAC on
    # the way across -- see device_target_name().
    def destination(path: Path) -> Path:
        return device / "Music" / device_target_name(path.relative_to(source))

    def is_wav(path: Path) -> bool:
        return path.suffix.lower() == ".wav"

    # A WAV's device copy is a re-encode, not a byte copy, so "is it already
    # there" is a presence-and-mtime check (needs_transcode). Every other
    # format is a byte copy, so copy_status can compare bytes and tell a real
    # change apart from a re-tag that only moved the timestamp: the latter
    # needs its mtime restamped, not the whole file pushed back over USB.
    pending = []               # copied or transcoded onto the device
    restampable = []           # identical bytes already there, mtime drifted
    for path in files:
        dst = destination(path)
        if is_wav(path):
            if needs_transcode(path, dst):
                pending.append(path)
        else:
            status = copy_status(path, dst)
            if status in ("absent", "differs"):
                pending.append(path)
            elif status == "stale-mtime":
                restampable.append((path, dst))
    unchanged = len(files) - len(pending) - len(restampable)

    if dry_run:
        for path in pending:
            rel = path.relative_to(source)
            if is_wav(path):
                print(f"  would convert  {rel} -> {device_target_name(rel)}")
            else:
                print(f"  would copy  {rel}")
        for path, _ in restampable:
            print(f"  would restamp  {path.relative_to(source)}  "
                  "(same audio, drifted timestamp)")
        print(f"\n{len(pending)} file(s) would be copied.")
        if restampable:
            print(f"{len(restampable)} file(s) already on the device; their "
                  "timestamps would be corrected without recopying.")
        if unchanged:
            print(f"{unchanged} file(s) already on the device, unchanged.")
        return 0

    def restamp_all() -> None:
        for src_path, dst_path in restampable:
            rel = src_path.relative_to(source)
            try:
                restamp(src_path, dst_path)
                if verbose:
                    print(f"  restamped  {rel}")
            except OSError as exc:
                print(f"  could not restamp {rel}: {exc}")

    if not pending:
        # Nothing would be written, so there's nothing to protect with a
        # backup either -- see backup_device()'s docstring. Restamping is a
        # directory-entry touch, not a data write, so it needs no backup.
        restamp_all()
        if restampable:
            print(f"Already up to date -- corrected {len(restampable)} "
                  f"timestamp(s), {unchanged} file(s) unchanged. Safe to disconnect.")
        else:
            print(f"Already up to date -- {unchanged} file(s) unchanged. "
                  "Safe to disconnect.")
        return 0

    backup = backup_device(device, BACKUP_ROOT)
    print(f"Backup: {backup}")

    failures = 0
    for path in pending:
        rel = path.relative_to(source)
        try:
            if is_wav(path):
                wav_to_flac(path, destination(path))
                if verbose:
                    print(f"  converted  {rel} -> {device_target_name(rel).name}")
            else:
                safe_copy(path, destination(path))
                if verbose:
                    print(f"  copied   {rel}")
        except Exception as exc:
            failures += 1
            print(f"  FAILED   {rel}: {exc}")

    restamp_all()

    copied = len(pending) - failures
    done = []
    if unchanged:
        done.append(f"{unchanged} already up to date")
    if restampable:
        done.append(f"{len(restampable)} timestamp(s) corrected")
    suffix = f", {', '.join(done)}" if done else ""
    print(f"Copied {copied} file(s){suffix}. Safe to disconnect.")
    if copied:
        # Found on a real Y1: a freshly copied track was missing from the
        # Music app right after unplugging, present again a bit later
        # with no restart. The device reindexes its library on its own
        # schedule, not the moment new files land on the drive.
        print("New tracks may take a minute or two to show up in the Y1's "
              "Music app — that's the device reindexing, not a failed copy.")
        # Found on a real Y1: opening a freshly added track for the first
        # time briefly shows a "file not supported" error, then plays it
        # correctly a couple of seconds later, cover art and all. Same
        # cause as the note above -- the device is still catching up.
        print("The first time you open a new track it may briefly say it's "
              "not supported before playing fine a couple seconds later — "
              "same reason, ignore it.")
    if failures:
        print(f"{failures} file(s) failed.")
        if failures == len(pending):
            return 1
    return 0


# An interactive prompt re-asks whenever it doesn't recognise the reply.
# Cap the re-asks: a stray multi-line paste -- an earlier screen pasted
# back into the prompt, a URL dragged in with half a web page -- otherwise
# feeds the loop hundreds of junk lines, each one redrawing the whole
# menu. Hitting the cap, or stdin ending (EOFError, or a frontend that
# just keeps handing back nothing), raises PromptAbort so the loop stops
# instead of spinning.
_MAX_PROMPT_RETRIES = 5


class PromptAbort(Exception):
    """A prompt gave up: stdin ended, or too many unrecognised replies."""


def _ask(question: str, input_fn, output_fn) -> str:
    """input_fn(question).strip(), with EOF turned into PromptAbort.

    A prompt read from a closed or exhausted stdin otherwise raises a bare
    EOFError that surfaces as a traceback. Callers pair this with the
    retry cap above so buffered junk can neither crash the prompt nor
    drive it without end.
    """
    try:
        return input_fn(question).strip()
    except EOFError:
        output_fn("")
        raise PromptAbort


def _prompt_for_music_folder(input_fn=input, output_fn=print) -> str:
    """Ask the user to pick a music folder, save it, and return it.

    Offers folders actually found on disk as numbered choices, so a first
    run never requires typing a path -- the thing that prompted this menu
    in the first place, on a keyboard where "~" is its own small ordeal.

    Raises PromptAbort if stdin ends or the reply is unrecognised
    _MAX_PROMPT_RETRIES times running.
    """
    for _ in range(_MAX_PROMPT_RETRIES):
        candidates = discover_music_folders(Path.home())
        output_fn("Where are your music files?")
        for index, folder in enumerate(candidates, start=1):
            output_fn(f"  {index}. {folder}")
        manual_option = len(candidates) + 1
        output_fn(f"  {manual_option}. Enter a path manually")

        reply = _ask("Choose a number: ", input_fn, output_fn)
        if not reply.isdigit():
            output_fn("Enter a number from the list.")
            continue
        choice = int(reply)
        if 1 <= choice <= len(candidates):
            folder = candidates[choice - 1]
        elif choice == manual_option:
            typed = _ask("Path to your music folder: ", input_fn, output_fn)
            folder = Path(typed).expanduser()
            if not folder.is_dir():
                output_fn(f"Not a folder: {folder}")
                continue
        else:
            output_fn("Enter a number from the list.")
            continue

        config = load_config()
        save_config(Config(acoustid_key=config.acoustid_key, music_folder=str(folder)))
        return str(folder)
    output_fn("Too many tries — giving up.")
    raise PromptAbort


def _load_yt2mp3():
    """Import yt2mp3's pieces lazily, or None if it isn't installed.

    yt2mp3 is a sibling tool, not a hard dependency of y1sync: importing it
    only when the download menu option is actually used keeps y1sync
    installable and testable entirely on its own.
    """
    try:
        from yt2mp3.checks import ensure_ffmpeg, FfmpegNotFoundError
        from yt2mp3.downloader import DownloadOptions, download
    except ImportError:
        return None
    return ensure_ffmpeg, FfmpegNotFoundError, DownloadOptions, download


# Bitrate menu: (label, kbps passed to yt2mp3), best first. The list
# position is the choice number; "0" cancels, Enter takes the first.
_BITRATE_OPTIONS = [
    ("320 kbps  (best, default)", "320"),
    ("256 kbps", "256"),
    ("192 kbps", "192"),
    ("128 kbps  (smallest files)", "128"),
]


def _prompt_bitrate(input_fn=input, output_fn=print) -> str | None:
    """Ask for an MP3 bitrate. Returns the kbps string, or None if cancelled.

    Raises PromptAbort if stdin ends or the reply is unrecognised
    _MAX_PROMPT_RETRIES times running.
    """
    for _ in range(_MAX_PROMPT_RETRIES):
        output_fn("Bitrate:")
        for index, (label, _kbps) in enumerate(_BITRATE_OPTIONS, start=1):
            output_fn(f"  {index}. {label}")
        output_fn("  0. Cancel")
        reply = _ask("Choose a number [1]: ", input_fn, output_fn)
        if reply == "":
            return _BITRATE_OPTIONS[0][1]
        if reply == "0":
            return None
        if reply.isdigit() and 1 <= int(reply) <= len(_BITRATE_OPTIONS):
            return _BITRATE_OPTIONS[int(reply) - 1][1]
        output_fn(f"Enter 1-{len(_BITRATE_OPTIONS)}, or 0 to cancel.")
    output_fn("Too many tries — giving up.")
    raise PromptAbort


def cmd_download_and_sync(folder: str, input_fn=input, output_fn=print) -> int:
    """Download a YouTube URL into folder via yt2mp3, then tag and sync it.

    The full flow in one menu choice: download, identify and tag, send to
    the device -- rather than requiring yt2mp3 and y1sync run separately.
    Cancelling at either prompt returns to the menu without downloading.
    """
    loaded = _load_yt2mp3()
    if loaded is None:
        output_fn("yt2mp3 isn't installed. Install it with: pip install ./yt2mp3")
        return 1
    ensure_ffmpeg, FfmpegNotFoundError, DownloadOptions, download = loaded

    try:
        ensure_ffmpeg()
    except FfmpegNotFoundError as exc:
        output_fn(str(exc))
        return 1

    url = _ask("YouTube URL (or 0 to cancel): ", input_fn, output_fn)
    if url in ("", "0"):
        output_fn("Cancelled.")
        return 0

    quality = _prompt_bitrate(input_fn, output_fn)
    if quality is None:
        output_fn("Cancelled.")
        return 0

    # yt2mp3 records the exact path of each MP3 it writes as it goes, so
    # that's what only is built from -- not a before/after directory
    # diff. A diff looks like the obvious way to find "the file(s) this
    # download just produced", but it silently misses a track whose
    # filename already existed (downloaded once before, or a retry after
    # an earlier attempt failed partway through): the path was already
    # there before, so nothing looks new, and the file is skipped
    # entirely -- never tagged, never sent to review, left on the device
    # exactly as un-tagged as it was before "Download from YouTube" ever
    # ran. `only` is what keeps cmd_scan from sweeping the whole music
    # folder and dragging every other unresolved track in there into
    # review too.
    downloaded_files: list[str] = []
    exit_code = download(
        DownloadOptions(url=url, output_dir=folder, quality=quality), downloaded_files
    )
    if exit_code != 0:
        output_fn("Download failed.")
        return exit_code
    new_files = {Path(p) for p in downloaded_files}

    cmd_scan(folder, dry_run=False, yes=False, verbose=False, only=new_files)
    cmd_sync(folder, dry_run=False, verbose=False)
    return 0


def cmd_menu(input_fn=input, output_fn=print) -> int:
    """The no-arguments entry point: a numbered menu instead of flags and paths.

    The scan/sync/doctor subcommands stay exactly as they are for anyone
    who wants them; this only wraps them for daily use once a music
    folder is on file.
    """
    config = load_config()
    folder = config.music_folder or _prompt_for_music_folder(input_fn, output_fn)

    misses = 0
    while True:
        output_fn("")
        output_fn("1. Download from YouTube  (then tag and send to player)")
        output_fn("2. Update player  (find new tracks, then send them over)")
        output_fn("3. Change music folder")
        output_fn("4. Check setup")
        output_fn("5. Check for updates")
        output_fn("6. Quit")
        reply = _ask("Choose a number: ", input_fn, output_fn)

        if reply == "1":
            cmd_download_and_sync(folder, input_fn, output_fn)
            output_fn("— back to the menu —")
        elif reply == "2":
            cmd_scan(folder, dry_run=False, yes=False, verbose=False)
            cmd_sync(folder, dry_run=False, verbose=False)
            output_fn("— back to the menu —")
        elif reply == "3":
            folder = _prompt_for_music_folder(input_fn, output_fn)
        elif reply == "4":
            cmd_doctor()
        elif reply == "5":
            cmd_check_for_updates(input_fn, output_fn)
            output_fn("— back to the menu —")
        elif reply == "6":
            return 0
        else:
            # Count only unrecognised replies in a row -- a real choice
            # resets it -- so a genuine session never trips the cap but a
            # wall of pasted junk still ends the loop.
            misses += 1
            if misses >= _MAX_PROMPT_RETRIES:
                output_fn("Too many tries — giving up.")
                raise PromptAbort
            output_fn("Enter a number from the list.")
            continue
        misses = 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        if args.command == "doctor":
            return cmd_doctor()
        if args.command == "scan":
            return cmd_scan(args.folder, args.dry_run, args.yes, args.verbose)
        if args.command == "sync":
            return cmd_sync(args.folder, args.dry_run, args.verbose)
        return cmd_menu()
    except KeyboardInterrupt:
        # Ctrl+C is how every interactive prompt here is meant to be
        # cancelled -- most just check for a "0" reply, but choose_candidate
        # has no cancel option of its own, so this is the only way out of
        # it. Without this, that Ctrl+C reaches input() unhandled and dumps
        # a raw traceback instead of just... stopping.
        print("\nCancelled.")
        return 130
    except PromptAbort:
        # A prompt hit EOF or a wall of unrecognised replies and bailed
        # (it has already said why). End quietly rather than by traceback.
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
