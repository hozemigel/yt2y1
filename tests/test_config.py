from y1sync.config import Config, load_config, save_config


def test_defaults_when_file_is_absent(tmp_path):
    config = load_config(tmp_path / "missing.toml")
    assert config == Config(acoustid_key=None)


def test_reads_values_from_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('acoustid_key = "abc123"\n', encoding="utf-8")
    config = load_config(path)
    assert config.acoustid_key == "abc123"


def test_unknown_keys_are_ignored(tmp_path):
    # A stale or mistyped key must not break startup.
    path = tmp_path / "config.toml"
    path.write_text('acoustid_key = "xyz"\nartwork_size = 300\n', encoding="utf-8")
    config = load_config(path)
    assert config.acoustid_key == "xyz"


def test_malformed_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not valid toml {{{", encoding="utf-8")
    assert load_config(path) == Config(None)


def test_reads_music_folder(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('music_folder = "/home/user/Music"\n', encoding="utf-8")
    assert load_config(path).music_folder == "/home/user/Music"


def test_save_creates_a_file_that_loads_back(tmp_path):
    path = tmp_path / "config.toml"
    save_config(Config(music_folder="/home/user/Music"), path)
    assert load_config(path).music_folder == "/home/user/Music"


def test_save_preserves_a_key_it_did_not_touch(tmp_path):
    path = tmp_path / "config.toml"
    save_config(Config(acoustid_key="abc123"), path)
    save_config(Config(music_folder="/home/user/Music"), path)
    reloaded = load_config(path)
    assert reloaded.acoustid_key == "abc123"
    assert reloaded.music_folder == "/home/user/Music"


def test_save_handles_a_path_with_backslashes_and_quotes(tmp_path):
    path = tmp_path / "config.toml"
    tricky = r'C:\Users\A "B"\Music'
    save_config(Config(music_folder=tricky), path)
    assert load_config(path).music_folder == tricky


def test_save_creates_missing_parent_directories(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    save_config(Config(music_folder="/home/user/Music"), path)
    assert load_config(path).music_folder == "/home/user/Music"
