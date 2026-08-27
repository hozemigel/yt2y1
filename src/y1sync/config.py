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
    return Config(acoustid_key=data.get("acoustid_key"))
