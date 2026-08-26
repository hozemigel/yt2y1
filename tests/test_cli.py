import pytest
from y1sync.cli import build_parser, main
from y1sync.models import Candidate, TrackMeta


def _confident_candidate() -> Candidate:
    """A candidate decide() will accept outright, no review needed."""
    return Candidate(
        meta=TrackMeta(artist="Artist", title="Title", album="Album"),
        confidence=0.95,
        source="acoustid",
        release_group_type="Album",
        secondary_types=(),
        release_status="Official",
        release_date="2020-01-01",
        artwork_url=None,
    )


def test_parser_accepts_the_three_subcommands():
    parser = build_parser()
    for command in ("doctor", "scan", "sync"):
        args = parser.parse_args([command] if command == "doctor" else [command, "."])
        assert args.command == command


def test_scan_accepts_dry_run():
    args = build_parser().parse_args(["scan", "/music", "--dry-run"])
    assert args.dry_run is True


def test_scan_accepts_yes():
    args = build_parser().parse_args(["scan", "/music", "--yes"])
    assert args.yes is True


def test_flags_default_to_false():
    args = build_parser().parse_args(["scan", "/music"])
    assert args.dry_run is False
    assert args.yes is False
    assert args.verbose is False


def test_no_arguments_exits_nonzero(capsys):
    assert main([]) != 0


def test_doctor_reports_status(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "ffmpeg" in out.lower() or "fpcalc" in out.lower()


def test_scan_on_empty_folder_succeeds(tmp_path, capsys):
    assert main(["scan", str(tmp_path)]) == 0
    assert "no mp3" in capsys.readouterr().out.lower()


def test_scan_on_missing_folder_fails(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "nope")]) != 0


def test_sync_without_a_device_fails(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("y1sync.cli.find_devices", lambda: [])
    assert main(["sync", str(tmp_path)]) != 0
    assert "no innioasis y1" in capsys.readouterr().out.lower()


def test_scan_continues_after_one_file_fails(tmp_path, capsys, monkeypatch):
    for name in ("a.mp3", "bad.mp3", "c.mp3"):
        # Distinct content per file: ContentCache keys on content hash, so
        # identical (empty) files would share a cache entry and mask
        # whether identify() was actually called for each one.
        (tmp_path / name).write_bytes(name.encode())

    def fake_identify(path, api_key=None, session=None):
        if path.name == "bad.mp3":
            raise ConnectionError("network unreachable")
        return [_confident_candidate()]

    monkeypatch.setattr("y1sync.cli.identify", fake_identify)
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "cache")

    exit_code = main(["scan", str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out.lower()

    # A partial failure is not a total failure.
    assert exit_code == 0
    # The failing file and its error are named, not swallowed.
    assert "bad.mp3" in out
    assert "network unreachable" in out
    # The good files either side of it were still processed.
    assert "a.mp3" in out
    assert "c.mp3" in out
    # The run reports how many files failed, so this can't masquerade
    # as "everything was fine".
    assert "1" in out and "failed" in out


def test_scan_dry_run_does_not_write_cache(tmp_path, capsys, monkeypatch):
    (tmp_path / "song.mp3").write_bytes(b"")
    cache_root = tmp_path / "cache"

    monkeypatch.setattr(
        "y1sync.cli.identify", lambda path, api_key=None, session=None: [_confident_candidate()]
    )
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", cache_root)

    assert main(["scan", str(tmp_path), "--dry-run"]) == 0

    identify_cache = cache_root / "identify"
    assert not list(identify_cache.glob("*.json"))
