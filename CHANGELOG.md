# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once past 1.0.

## [Unreleased]

### Fixed
- **Cover art lookup no longer matches an unrelated same-named artist
  when the album is unknown.** Searching iTunes for just an artist's name
  — the fallback when no album is known — matched whatever album ranked
  top for that name, regardless of whether it was the right artist.
  Found for real: "Electric Youth" with no album came back with Debbie
  Gibson's 1989 album of the same name, nothing to do with the actual
  track. That search term is no longer tried at all when there's no
  album; artist + title is tried first instead.
- **Cover art lookup also now tries the title with a trailing qualifier
  stripped.** "(Radio Edit)", "(House Remix)", "(Live Session)" and
  similar describe a specific version, not a release with its own iTunes
  listing — searching with one still attached often finds nothing even
  though the underlying song has an official cover on file. Tried last,
  after the exact title.
- **A copy that silently landed as a 0-byte file is now a loud, retriable
  failure instead of a false "Copied."** Found for real on a Y1, plugged
  in and untouched throughout: a track's copy raised no error and was
  never interrupted, and still ended up present at the right name with
  the right size reported... except the file itself was empty --
  "Unknown" artist, no cover, because there were no ID3 tags left to read.
  `safe_copy()` now checks the actual byte count landed at both the write
  and the rename, and raises if either comes up short, so `y1sync sync`
  reports it as `FAILED` and a later run's `needs_copy()` (size differs)
  retries it -- rather than the file sitting silently broken on the
  device until someone notices the missing cover art.
- **Downloading one track no longer drags unrelated ones into review.**
  "Download from YouTube" used to re-scan the entire music folder after the
  download finished, so any other track already sitting there unresolved —
  including one already on the Y1 from before — would surface for review
  too, unconnected to what was just downloaded. It now only tags and syncs
  the file it just downloaded, using the exact path yt2mp3 reports having
  written rather than comparing a directory listing before and after (that
  comparison has its own bug: a track downloaded a second time, or retried
  after an earlier attempt failed partway through, writes to a filename
  that already exists — a before/after diff sees no new path there and
  silently drops the file, leaving it untagged with no cover art). "Update
  player" is unaffected: it still sweeps the whole folder, which is the
  point there.
- **Ctrl+C during a review prompt no longer dumps a traceback.** It's now
  caught cleanly and prints "Cancelled."

### Added
- **A track the fingerprint can't place is now identified from what
  YouTube said it was, not just its filename.** `yt2mp3` writes a small
  `<name>.yt2mp3.json` beside each download holding the artist, title,
  album and year yt-dlp pulled from the video (a YouTube Music "- Topic"
  channel, or the "Provided to YouTube by" block in the description).
  When AcoustID returns no match — common for lesser-known and
  independent tracks — `y1sync` uses that to text-search MusicBrainz for
  the real release and to seed the iTunes lookup, instead of guessing
  from a noisy filename. The result still goes to review and `--yes`
  still refuses it: nothing but a fingerprint is applied unseen. No
  sidecar (a hand-managed library, or a file downloaded another way)
  means the old filename behaviour, unchanged.
- **The installers now set up deno**, a JS runtime yt-dlp uses for
  reliable YouTube extraction. Without one, downloads fall back to a
  slower, more failure-prone path — seen for real as repeated read
  timeouts fetching YouTube's player API and a download that cuts off
  partway through. Not a hard requirement — YouTube downloads still work
  without it, just less reliably — so `y1sync doctor` reports it as
  recommended rather than blocking readiness on it.
- yt2mp3's downloads are more resilient to a slow or flaky connection:
  yt-dlp's socket timeout and retry counts are both raised.
- **A "Check for updates" menu option.** Fetches the cloned repo, reports
  how many commits behind origin it is, and offers to pull and reinstall
  both tools in place. Works with the standard install (see the
  installers above); a checkout in a different location is told so
  rather than guessed at.

## [0.1.0] - 2026-08-28

Initial tagged release. Both tools have been run end to end against the real
AcoustID and MusicBrainz services and against an Innioasis Y1.

### Added
- **yt2mp3** — download a YouTube video or playlist as MP3 at a chosen bitrate.
- **y1sync** — identify tracks by audio fingerprint (AcoustID + MusicBrainz),
  tag and rename them, and sync a library to the Y1 over USB: the folder tree
  is preserved, unchanged files are skipped, and the device is backed up
  before anything is written. Release ranking prefers the original album over
  compilations, live albums and remixes, and anything ambiguous goes to a
  review prompt rather than being guessed.
- One-line installers for Windows (`install-windows.ps1`), Linux
  (`install-linux.sh`) and macOS (`install-macos.sh`), plus `y1sync doctor` to
  report whether dependencies and the device are ready.

### Changed
- **No AcoustID key to set up.** y1sync now ships with its own AcoustID lookup
  key, so fingerprint identification works the moment it's installed. The
  installers no longer pause to walk you through registering an application
  key, and `y1sync doctor` no longer checks for one — just `ffmpeg` and
  `chromaprint`. If the built-in key is ever rate-limited, you can still point
  y1sync at your own by setting `acoustid_key` in
  `~/.config/y1sync/config.toml`. (AcoustID's lookup API authenticates the
  application, not the user, so one shared key is all a read-only client can
  use.)

### Fixed
- **A short edit is no longer silently tagged as the full-length original.** An
  AcoustID fingerprint only covers a track's first ~120 seconds, so a radio
  edit or a sped-up rip can match the same recording as the complete song.
  y1sync now compares the file's length against the matched recording's: if
  they differ by more than 30 seconds, the match goes to review — with both
  durations shown — instead of being applied automatically. `--yes` refuses
  these the same way it refuses filename-only guesses. Matches with no length
  information on either side are unaffected.

[0.1.0]: https://github.com/hozemigel/yt2y1/releases/tag/v0.1.0
