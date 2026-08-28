# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once past 1.0.

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
