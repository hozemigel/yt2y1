from y1sync.config import Config, load_config


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
