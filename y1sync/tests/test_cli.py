from pathlib import Path

import pytest
from y1sync.cli import build_parser, cmd_menu, discover_music_folders, main
from y1sync.config import Config, load_config, save_config
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


def test_no_arguments_launches_the_menu(monkeypatch):
    calls = []
    monkeypatch.setattr("y1sync.cli.cmd_menu", lambda: calls.append(True) or 0)
    assert main([]) == 0
    assert calls == [True]


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


def test_scan_recurses_into_subdirectories(tmp_path, capsys, monkeypatch):
    # "y1sync scan ~/Music" on a library organised into folders must not
    # report "No MP3 files".
    nested = tmp_path / "Black" / "Wonderful Life"
    nested.mkdir(parents=True)
    (nested / "rip.mp3").write_bytes(b"nested audio")

    _stub_scan_side_effects(monkeypatch, tmp_path)
    assert main(["scan", str(tmp_path)]) == 0

    out = capsys.readouterr().out.lower()
    assert "no mp3" not in out
    assert (nested / "Artist - Title.mp3").exists()


def test_scan_collisions_are_scoped_to_each_directory(tmp_path, monkeypatch):
    # Two files in different folders identify to the same name. Neither is
    # in the other's way, so neither gets a " (2)" suffix.
    for folder in ("one", "two"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "rip.mp3").write_bytes(folder.encode())

    _stub_scan_side_effects(monkeypatch, tmp_path)
    assert main(["scan", str(tmp_path)]) == 0

    assert (tmp_path / "one" / "Artist - Title.mp3").exists()
    assert (tmp_path / "two" / "Artist - Title.mp3").exists()


def test_scan_dry_run_previews_the_whole_tree(tmp_path, capsys, monkeypatch):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "rip.mp3").write_bytes(folder.encode())

    _stub_scan_side_effects(monkeypatch, tmp_path)
    assert main(["scan", str(tmp_path), "--dry-run"]) == 0

    out = capsys.readouterr().out
    # Relative paths, so two files both called rip.mp3 stay distinguishable.
    assert "a/rip.mp3" in out.replace("\\", "/")
    assert "b/rip.mp3" in out.replace("\\", "/")
    assert "2 file(s)" in out


def _fake_device(tmp_path):
    from y1sync.device import Y1_SIGNATURE
    device = tmp_path / "Y1"
    for folder in Y1_SIGNATURE:
        (device / folder).mkdir(parents=True)
    return device


def test_sync_recurses_and_preserves_the_tree(tmp_path, capsys, monkeypatch):
    device = _fake_device(tmp_path)
    source = tmp_path / "library"
    (source / "Black").mkdir(parents=True)
    (source / "Black" / "Wonderful Life.mp3").write_bytes(b"nested audio")
    (source / "top.mp3").write_bytes(b"top audio")

    monkeypatch.setattr("y1sync.cli.find_devices", lambda: [device])
    monkeypatch.setattr("y1sync.cli.BACKUP_ROOT", tmp_path / "backups")

    assert main(["sync", str(source)]) == 0

    copied = device / "Music" / "Black" / "Wonderful Life.mp3"
    assert copied.read_bytes() == b"nested audio"
    assert (device / "Music" / "top.mp3").read_bytes() == b"top audio"

    out = capsys.readouterr().out
    assert "reindexing" in out
    assert "not supported" in out


def test_sync_with_no_files_skips_the_reindexing_note(tmp_path, capsys, monkeypatch):
    device = _fake_device(tmp_path)
    source = tmp_path / "library"
    source.mkdir()

    monkeypatch.setattr("y1sync.cli.find_devices", lambda: [device])
    monkeypatch.setattr("y1sync.cli.BACKUP_ROOT", tmp_path / "backups")

    assert main(["sync", str(source)]) == 0

    out = capsys.readouterr().out
    assert "reindexing" not in out
    assert "not supported" not in out


def test_sync_dry_run_previews_the_whole_tree(tmp_path, capsys, monkeypatch):
    device = _fake_device(tmp_path)
    source = tmp_path / "library"
    (source / "Black").mkdir(parents=True)
    (source / "Black" / "Wonderful Life.mp3").write_bytes(b"nested audio")

    monkeypatch.setattr("y1sync.cli.find_devices", lambda: [device])
    monkeypatch.setattr("y1sync.cli.BACKUP_ROOT", tmp_path / "backups")

    assert main(["sync", str(source), "--dry-run"]) == 0

    out = capsys.readouterr().out.replace("\\", "/")
    assert "Black/Wonderful Life.mp3" in out
    assert "1 file(s)" in out
    # --dry-run writes nothing anywhere, including no backup.
    assert not (tmp_path / "backups").exists()
    assert not any((device / "Music").iterdir())


# --- --yes must not accept filename guesses ----------------------------
#
# Found by running the tool on a real library before fingerprinting was
# configured: --yes accepted all 14 tracks at confidence 0.0, including
# Counting Crows in place of Harry Styles. --yes is meant to skip choosing
# between plausible releases of a recording the audio has confirmed, not
# to rubber-stamp a guess made from YouTube debris in a filename.


def _guess_candidate(artist="Counting Crows", title="American Girls"):
    """What the iTunes fallback produces: no audio ever confirmed it."""
    return Candidate(
        meta=TrackMeta(artist=artist, title=title, album="Hard Candy"),
        confidence=0.0, source="itunes", release_group_type="Album",
        release_status="Official", release_date="2002-01-01",
    )


def _two_guesses():
    return [_guess_candidate(), _guess_candidate("Harry Styles", "American Girls")]


def test_yes_refuses_to_accept_a_filename_guess(tmp_path, capsys, monkeypatch):
    (tmp_path / "Harry Styles - American Girls.mp3").write_bytes(b"one")
    monkeypatch.setattr("y1sync.cli.identify",
                        lambda p, api_key=None, session=None: _two_guesses())
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "cache")

    main(["scan", str(tmp_path), "--dry-run", "--yes"])
    out = capsys.readouterr().out.lower()

    assert "needs review" in out
    # It must not have quietly written the wrong artist.
    assert "would tag and rename" not in out


def test_yes_explains_what_to_do_about_refused_tracks(tmp_path, capsys, monkeypatch):
    (tmp_path / "song.mp3").write_bytes(b"one")
    monkeypatch.setattr("y1sync.cli.identify",
                        lambda p, api_key=None, session=None: _two_guesses())
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "cache")

    main(["scan", str(tmp_path), "--dry-run", "--yes"])
    out = capsys.readouterr().out.lower()

    # A refusal the user cannot act on is just an obstruction.
    assert "without --yes" in out
    assert "doctor" in out


def test_yes_still_accepts_a_fingerprinted_track(tmp_path, capsys, monkeypatch):
    # The flag keeps working for what it is actually for: choosing among
    # releases of a recording the audio confirmed.
    (tmp_path / "song.mp3").write_bytes(b"one")

    def two_releases(path, api_key=None, session=None):
        return [
            Candidate(meta=TrackMeta(artist="Shaggy", title="Angel", album="Hot Shot"),
                      confidence=0.97, source="acoustid", release_group_type="Album",
                      release_status="Official", release_date="2000-08-08"),
            Candidate(meta=TrackMeta(artist="Shaggy", title="Angel", album="Boombastic"),
                      confidence=0.97, source="acoustid", release_group_type="Album",
                      secondary_types=("Compilation",),
                      release_status="Official", release_date="2008-01-01"),
        ]

    monkeypatch.setattr("y1sync.cli.identify", two_releases)
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "cache")

    main(["scan", str(tmp_path), "--dry-run", "--yes"])
    out = capsys.readouterr().out

    assert "would tag and rename" in out
    # And it says which ambiguous choice it made on the user's behalf.
    assert "Hot Shot" in out


# --- discover_music_folders ---------------------------------------------


def test_discovers_a_folder_containing_mp3s(tmp_path):
    music = tmp_path / "Music"
    music.mkdir()
    (music / "song.mp3").write_bytes(b"x")

    found = discover_music_folders(tmp_path)

    assert music in found


def test_ignores_folders_with_no_mp3s(tmp_path):
    (tmp_path / "Photos").mkdir()
    (tmp_path / "Photos" / "pic.jpg").write_bytes(b"x")

    assert discover_music_folders(tmp_path) == []


def test_skips_hidden_directories(tmp_path):
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "song.mp3").write_bytes(b"x")

    assert discover_music_folders(tmp_path) == []


def test_common_folder_names_surface_first(tmp_path):
    deep = tmp_path / "some" / "deeply" / "nested" / "folder"
    deep.mkdir(parents=True)
    (deep / "song.mp3").write_bytes(b"x")
    music = tmp_path / "Music"
    music.mkdir()
    (music / "song.mp3").write_bytes(b"x")

    found = discover_music_folders(tmp_path)

    assert found[0] == music


def test_respects_the_limit(tmp_path):
    for n in range(10):
        folder = tmp_path / f"Album{n}"
        folder.mkdir()
        (folder / "song.mp3").write_bytes(b"x")

    assert len(discover_music_folders(tmp_path, limit=3)) == 3


# --- interactive menu ----------------------------------------------------


def _config_path(tmp_path):
    return tmp_path / "config.toml"


def test_first_run_prompts_for_a_folder_and_saves_it(tmp_path, monkeypatch):
    monkeypatch.setattr("y1sync.config.default_config_path", lambda: _config_path(tmp_path))
    music = tmp_path / "Music"
    music.mkdir()
    monkeypatch.setattr("y1sync.cli.discover_music_folders", lambda root, limit=6: [music])

    replies = iter(["1", "4"])  # pick the discovered folder, then quit
    lines = []
    cmd_menu(input_fn=lambda _: next(replies), output_fn=lines.append)

    assert load_config(_config_path(tmp_path)).music_folder == str(music)
    assert any("Where are your music files?" in line for line in lines)


def test_a_saved_folder_skips_the_first_run_prompt(tmp_path, monkeypatch):
    path = _config_path(tmp_path)
    monkeypatch.setattr("y1sync.config.default_config_path", lambda: path)
    save_config(Config(music_folder=str(tmp_path)), path)

    lines = []
    cmd_menu(input_fn=lambda _: "4", output_fn=lines.append)

    assert not any("Where are your music files?" in line for line in lines)


def test_menu_option_1_scans_then_syncs(tmp_path, monkeypatch):
    path = _config_path(tmp_path)
    monkeypatch.setattr("y1sync.config.default_config_path", lambda: path)
    save_config(Config(music_folder=str(tmp_path)), path)

    calls = []
    monkeypatch.setattr("y1sync.cli.cmd_scan", lambda folder, **kw: calls.append(("scan", folder)))
    monkeypatch.setattr("y1sync.cli.cmd_sync", lambda folder, **kw: calls.append(("sync", folder)))

    replies = iter(["1", "4"])
    cmd_menu(input_fn=lambda _: next(replies), output_fn=lambda *a: None)

    assert calls == [("scan", str(tmp_path)), ("sync", str(tmp_path))]


def test_menu_option_3_checks_setup(tmp_path, monkeypatch):
    path = _config_path(tmp_path)
    monkeypatch.setattr("y1sync.config.default_config_path", lambda: path)
    save_config(Config(music_folder=str(tmp_path)), path)

    calls = []
    monkeypatch.setattr("y1sync.cli.cmd_doctor", lambda: calls.append("doctor"))

    replies = iter(["3", "4"])
    cmd_menu(input_fn=lambda _: next(replies), output_fn=lambda *a: None)

    assert calls == ["doctor"]


def test_menu_rejects_an_invalid_choice_and_reprompts(tmp_path, monkeypatch):
    path = _config_path(tmp_path)
    monkeypatch.setattr("y1sync.config.default_config_path", lambda: path)
    save_config(Config(music_folder=str(tmp_path)), path)

    lines = []
    replies = iter(["banana", "4"])
    result = cmd_menu(input_fn=lambda _: next(replies), output_fn=lines.append)

    assert result == 0
    assert any("Enter a number" in line for line in lines)


def test_menu_option_2_changes_the_saved_folder(tmp_path, monkeypatch):
    path = _config_path(tmp_path)
    monkeypatch.setattr("y1sync.config.default_config_path", lambda: path)
    save_config(Config(music_folder=str(tmp_path)), path)

    new_folder = tmp_path / "Elsewhere"
    new_folder.mkdir()
    # No discovered folders offered, so option 1 is "enter a path manually".
    monkeypatch.setattr("y1sync.cli.discover_music_folders", lambda root, limit=6: [])

    inputs = iter(["2", "1", str(new_folder), "4"])
    cmd_menu(input_fn=lambda _: next(inputs), output_fn=lambda *a: None)

    assert load_config(path).music_folder == str(new_folder)
