from y1sync.config import Config, load_config


def test_defaults_when_file_is_absent(tmp_path):
    config = load_config(tmp_path / "missing.toml")
    assert config == Config(acoustid_key=None, artwork_size=600, music_dir=None)


def test_reads_values_from_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'acoustid_key = "abc123"\n'
        "artwork_size = 300\n"
        'music_dir = "/home/user/Music"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.acoustid_key == "abc123"
    assert config.artwork_size == 300
    assert config.music_dir == "/home/user/Music"


def test_partial_file_keeps_other_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('acoustid_key = "xyz"\n', encoding="utf-8")
    config = load_config(path)
    assert config.acoustid_key == "xyz"
    assert config.artwork_size == 600


def test_malformed_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not valid toml {{{", encoding="utf-8")
    assert load_config(path) == Config(None, 600, None)
