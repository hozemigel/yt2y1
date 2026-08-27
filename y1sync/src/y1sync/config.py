"""User configuration, read from ~/.config/y1sync/config.toml."""

import sys
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    import tomllib
else:  # tomllib landed in 3.11; tomli is the identical backport.
    import tomli as tomllib

from pathlib import Path

@dataclass(frozen=True)
class Config:
    acoustid_key: str | None = None
    music_folder: str | None = None


def default_config_path() -> Path:
    return Path.home() / ".config" / "y1sync" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    """Load configuration, falling back to defaults.

    A missing or malformed file is not fatal: the tool works without any
    configuration, it just cannot fingerprint.
    """
    path = Path(path) if path is not None else default_config_path()
    if not path.is_file():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return Config()
    return Config(acoustid_key=data.get("acoustid_key"), music_folder=data.get("music_folder"))


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_config(config: Config, path: Path | None = None) -> None:
    """Write config back to disk.

    Existing keys this version of Config does not know about are read
    back and re-written unchanged, so an older field is not silently
    dropped by a save that only meant to change one thing.
    """
    path = Path(path) if path is not None else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (tomllib.TOMLDecodeError, OSError):
        data = {}

    if config.acoustid_key is not None:
        data["acoustid_key"] = config.acoustid_key
    if config.music_folder is not None:
        data["music_folder"] = config.music_folder

    lines = ["# y1sync configuration"]
    lines += [f"{key} = {_toml_string(value)}" for key, value in data.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
