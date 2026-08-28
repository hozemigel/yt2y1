# yt2mp3

Download a YouTube video or playlist and convert it to MP3.

## Requirements

- **Python 3.10+**
- **ffmpeg**, for the actual audio conversion:
  ```bash
  brew install ffmpeg          # macOS
  sudo apt install ffmpeg      # Debian, Ubuntu
  ```
  Windows: download a build from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
  and add its `bin` folder to your PATH. `yt2mp3` checks for it on startup
  and tells you if it's missing.
- `yt-dlp`, the actual downloader — installed automatically as a dependency, nothing to do here.

## Install

```bash
pip install ./yt2mp3
```

(from the root of this repo — or `pip install .` from inside the `yt2mp3/` folder itself)

## Use

```bash
yt2mp3 "https://www.youtube.com/watch?v=..."
```

By default this saves one MP3 to `~/yt2mp3/pesme/`, at 320kbps, named after
the video's title.

### Options

```
-o, --output DIR         Output directory (default: ~/yt2mp3/pesme)
-q, --quality KBPS        MP3 bitrate (default: 320)
--filename-template TPL   yt-dlp output filename template (default: %(title)s.%(ext)s)
--playlist                Download the whole playlist, not just the one video
```

### The playlist trap

Only the exact video is downloaded by default, **even if the URL contains
a `list=` parameter** — which happens more often than it looks. Opening any
video from a YouTube-generated "Mix" (the auto-play queue YouTube builds
next to a video) puts a `list=RD...` parameter on that video's own URL, and
pasting that URL here would otherwise pull in the *entire* mix — often
several hundred tracks — instead of the one song you meant.

If you actually want a playlist, pass `--playlist` explicitly:

```bash
yt2mp3 "https://www.youtube.com/playlist?list=PLxxxxxxxx" --playlist
```

## The metadata sidecar

Next to every MP3 it writes, `yt2mp3` leaves a `<name>.yt2mp3.json` file
with the artist, title, album and year yt-dlp extracted from the video.
It costs nothing if you don't use it, and it's what lets `y1sync`
identify a track that audio fingerprinting can't place without falling
back to guessing from the filename. Delete them freely; they're
regenerated on the next download.

## Licence

MIT
