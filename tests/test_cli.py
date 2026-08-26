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


def _stub_scan_side_effects(monkeypatch, tmp_path, candidate=None):
    """Neutralise everything scan does except identification and renaming."""
    pick = candidate or _confident_candidate()
    monkeypatch.setattr(
        "y1sync.cli.identify", lambda path, api_key=None, session=None: [pick]
    )
    monkeypatch.setattr("y1sync.cli.artwork_url_for", lambda meta, session=None: None)
    monkeypatch.setattr(
        "y1sync.cli.fetch_artwork", lambda url, cache_dir, session=None: None
    )
    monkeypatch.setattr("y1sync.cli.write_tags", lambda path, meta, artwork=None: None)
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "cache")


def test_scan_never_overwrites_an_existing_file(tmp_path, capsys, monkeypatch):
    # A folder holding an already-correct file plus a second rip of the
    # same track. Both identify to "Artist - Title.mp3"; both must survive.
    # The rip sorts first, so processing order alone cannot save the
    # already-correct file: only consulting the filesystem can.
    good = tmp_path / "Artist - Title.mp3"
    good.write_bytes(b"the good copy")
    rip = tmp_path / "Alpha rip.mp3"
    rip.write_bytes(b"the second rip")

    _stub_scan_side_effects(monkeypatch, tmp_path)
    assert main(["scan", str(tmp_path)]) == 0

    names = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".mp3")
    assert names == ["Artist - Title (2).mp3", "Artist - Title.mp3"]
    assert (tmp_path / "Artist - Title.mp3").read_bytes() == b"the good copy"
    assert (tmp_path / "Artist - Title (2).mp3").read_bytes() == b"the second rip"


def test_rescanning_an_already_correct_file_is_a_no_op(tmp_path, capsys, monkeypatch):
    # The second run of scan on a folder it already tidied must not
    # rename "Artist - Title.mp3" to "Artist - Title (2).mp3".
    correct = tmp_path / "Artist - Title.mp3"
    correct.write_bytes(b"audio")

    _stub_scan_side_effects(monkeypatch, tmp_path)
    assert main(["scan", str(tmp_path)]) == 0

    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".mp3"] == [
        "Artist - Title.mp3"
    ]
    assert correct.read_bytes() == b"audio"


def _ambiguous_candidates() -> list[Candidate]:
    """Two releases of one recording: decide() must route this to review."""
    base = _confident_candidate()
    other = Candidate(
        meta=TrackMeta(artist="Artist", title="Title", album="Greatest Hits"),
        confidence=0.95,
        source="acoustid",
        release_group_type="Album",
        secondary_types=("Compilation",),
        release_status="Official",
        release_date="1995-01-01",
        artwork_url=None,
    )
    return [base, other]


def test_scan_does_not_re_ask_a_question_already_answered(tmp_path, monkeypatch):
    (tmp_path / "rip.mp3").write_bytes(b"some audio")
    _stub_scan_side_effects(monkeypatch, tmp_path)

    lookups: list[str] = []
    prompts: list[str] = []

    def counting_identify(path, api_key=None, session=None):
        lookups.append(path.name)
        return _ambiguous_candidates()

    def counting_choose(path, candidates, **kwargs):
        prompts.append(path.name)
        return candidates[0]

    monkeypatch.setattr("y1sync.cli.identify", counting_identify)
    monkeypatch.setattr("y1sync.cli.choose_candidate", counting_choose)

    assert main(["scan", str(tmp_path)]) == 0
    assert len(lookups) == 1 and len(prompts) == 1

    # The second run must reuse both the lookup and the answer.
    assert main(["scan", str(tmp_path)]) == 0
    assert len(lookups) == 1, "re-queried the network for a cached track"
    assert len(prompts) == 1, "re-asked a question already answered"


def test_doctor_reports_the_cache_location(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "somecache")
    assert main(["doctor"]) == 0
    # A remembered choice is sticky, so the user has to be told where to
    # clear it.
    assert "somecache" in capsys.readouterr().out
