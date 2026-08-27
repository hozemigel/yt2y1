# yt2y1

Download music from YouTube and get it onto an [Innioasis Y1](https://www.innioasis.com/) player, correctly tagged.

Two small tools, each doing one job:

- **[yt2mp3](yt2mp3/)** — download a YouTube video or playlist as MP3.
- **[y1sync](y1sync/)** — identify, tag, and sync a music library to the Y1 by audio fingerprint rather than filename, so a mislabeled download doesn't end up mislabeled on the device.

## Install

```bash
pip install ./yt2mp3
pip install ./y1sync
```

See each tool's own README for setup (y1sync's fingerprinting needs `chromaprint` and a free AcoustID key) and usage.

## Typical flow

```bash
yt2mp3 "https://youtube.com/watch?v=..."   # -> ~/yt2mp3/pesme/*.mp3
y1sync                                      # menu: tag, then send to the device
```
