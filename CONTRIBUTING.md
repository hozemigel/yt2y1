# Contributing

## Setup

```bash
git clone https://github.com/lukamilicevic/y1sync
cd y1sync
pip install -e ".[dev]"
pytest
```

## Ground rules

- All code, comments, and user-facing text are in English.
- Tests come first. Every bug fix starts with a test that reproduces it.
- Tests must not touch the network or a real device. Use fixtures.
- Y1 only. Support for other players is out of scope — see the design doc
  in `docs/superpowers/specs/`.

## Testing on a real device

The test suite never writes to hardware. If you have verified a change on
a real Y1, say so in the pull request, including the firmware version.
