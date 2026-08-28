# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once past 1.0.

## [Unreleased]

### Fixed
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
