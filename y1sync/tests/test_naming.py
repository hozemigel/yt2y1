import pytest
from pathlib import Path
from y1sync.models import TrackMeta
from y1sync.naming import (
    sanitize_component, safe_filename, resolve_collision, rename_file,
)


def test_maps_unicode_slash_lookalikes():
    # U+29F8 appears in YouTube rips where a real slash was intended.
    assert sanitize_component("7⧸4⧸2004") == "7-4-2004"


def test_replaces_characters_illegal_on_fat32():
    assert sanitize_component('a<b>c:d"e/f\\g|h?i*j') == "a-b-c-d-e-f-g-h-i-j"


def test_strips_control_characters():
    assert sanitize_component("a\x00b\x1fc") == "a-b-c"


def test_collapses_whitespace_and_trims_dots():
    assert sanitize_component("  Hello   World . ") == "Hello World"


@pytest.mark.parametrize("reserved", ["CON", "PRN", "AUX", "NUL", "COM1", "LPT9"])
def test_rejects_windows_reserved_names(reserved):
    meta = TrackMeta(artist=reserved, title=reserved, album="X")
    name = safe_filename(meta)
    stem = name[:-len(".mp3")]
    assert stem.upper() not in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT9"}
    assert name.endswith(".mp3")


def test_reserved_name_check_is_case_insensitive():
    meta = TrackMeta(artist="", title="aux", album="X")
    assert safe_filename(meta) != "aux.mp3"


def test_builds_artist_title_format():
    meta = TrackMeta(artist="Tracy Chapman", title="Fast Car", album="Tracy Chapman")
    assert safe_filename(meta) == "Tracy Chapman - Fast Car.mp3"


def test_truncates_to_max_length():
    meta = TrackMeta(artist="A" * 80, title="B" * 80, album="X")
    name = safe_filename(meta, max_len=100)
    assert len(name) <= 100 + len(".mp3")


def test_keeps_the_source_extension():
    meta = TrackMeta(artist="Boards of Canada", title="Roygbiv", album="Music Has the Right")
    assert safe_filename(meta, ".flac") == "Boards of Canada - Roygbiv.flac"


def test_lower_cases_the_extension():
    meta = TrackMeta(artist="A", title="B", album="X")
    assert safe_filename(meta, ".OGG") == "A - B.ogg"


def test_extension_defaults_to_mp3():
    meta = TrackMeta(artist="A", title="B", album="X")
    assert safe_filename(meta) == "A - B.mp3"


def test_resolve_collision_appends_counter():
    taken = {"song.mp3"}
    assert resolve_collision("song.mp3", taken) == "song (2).mp3"


def test_resolve_collision_is_case_insensitive():
    # FAT32 does not distinguish case, so neither may collision detection.
    taken = {"song.mp3"}
    assert resolve_collision("SONG.mp3", taken) == "SONG (2).mp3"


def test_case_only_rename_succeeds(tmp_path):
    # The bug this guards against: on a case-insensitive filesystem a naive
    # os.rename from "Black" to "BLACK" is a silent no-op.
    src = tmp_path / "Black - Wonderful Life.mp3"
    src.write_bytes(b"data")
    result = rename_file(src, "BLACK - Wonderful Life.mp3")
    assert result.name == "BLACK - Wonderful Life.mp3"
    assert result.read_bytes() == b"data"
    assert len(list(tmp_path.iterdir())) == 1


def test_case_only_rename_with_fat32_semantics(tmp_path, monkeypatch):
    # test_case_only_rename_succeeds cannot catch the regression on case-sensitive
    # filesystems (ext4, etc.) because "Black" → "BLACK" succeeds there. This test
    # forces FAT32 semantics: a rename differing only by case is a silent no-op,
    # and rename_file must detect this and use the two-step workaround.
    original_rename = Path.rename

    def fat32_rename(self, target):
        """Mimic FAT32: case-only renames are silent no-ops."""
        target_path = Path(target) if not isinstance(target, Path) else target
        if self.name.lower() == target_path.name.lower() and self.name != target_path.name:
            # Case-only change on FAT32: silently do nothing
            return
        # Normal rename
        original_rename(self, target)

    monkeypatch.setattr(Path, "rename", fat32_rename)

    src = tmp_path / "Black - Wonderful Life.mp3"
    src.write_bytes(b"data")
    result = rename_file(src, "BLACK - Wonderful Life.mp3")

    # Even though Path.rename silently did nothing for the case-only change,
    # rename_file's two-step workaround should make the file have the new name
    assert result.name == "BLACK - Wonderful Life.mp3"
    assert result.read_bytes() == b"data"
    assert len(list(tmp_path.iterdir())) == 1


def test_rename_to_identical_name_is_a_noop(tmp_path):
    src = tmp_path / "song.mp3"
    src.write_bytes(b"data")
    assert rename_file(src, "song.mp3") == src


def test_rename_refuses_to_overwrite_a_different_file(tmp_path):
    # Path.rename overwrites atomically and silently. A rename onto an
    # occupied name would destroy the file already there.
    victim = tmp_path / "Black - Wonderful Life.mp3"
    victim.write_bytes(b"the good copy")
    newcomer = tmp_path / "rip.mp3"
    newcomer.write_bytes(b"the new rip")

    with pytest.raises(FileExistsError):
        rename_file(newcomer, "Black - Wonderful Life.mp3")

    assert victim.read_bytes() == b"the good copy"
    assert newcomer.read_bytes() == b"the new rip"


def test_rename_to_the_same_name_is_a_no_op(tmp_path):
    path = tmp_path / "Black - Wonderful Life.mp3"
    path.write_bytes(b"audio")
    assert rename_file(path, "Black - Wonderful Life.mp3") == path
    assert path.read_bytes() == b"audio"


# --- Unicode folding tests ---

def test_typographic_hyphen_folds_to_ascii():
    # U+2010 HYPHEN (not U+002D ASCII hyphen) must become "-".
    assert sanitize_component("a‐ha") == "a-ha"


def test_right_single_quotation_folds_to_ascii():
    # U+2019 RIGHT SINGLE QUOTATION MARK must become "'".
    assert sanitize_component("It Ain’t Me") == "It Ain't Me"


def test_nfkd_strips_combining_marks_latin():
    # U+012A LATIN CAPITAL LETTER I WITH MACRON decomposes under NFKD to I + combining macron.
    assert sanitize_component("AVĪCI") == "AVICI"
    # U+00E9 LATIN SMALL LETTER E WITH ACUTE decomposes to e + combining acute.
    assert sanitize_component("Beyoncé") == "Beyonce"


def test_nfkd_leaves_cyrillic_intact():
    # Scripts with no ASCII decomposition must not be destroyed.
    assert sanitize_component("Кино") == "Кино"


def test_safe_filename_with_typographic_hyphen_in_artist():
    # End-to-end: a‐ha (U+2010) in artist field → file uses ASCII hyphen.
    meta = TrackMeta(artist="a‐ha", title="Stay on These Roads", album="X")
    assert safe_filename(meta) == "a-ha - Stay on These Roads.mp3"
