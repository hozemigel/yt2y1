import yt2mp3.cli as cli


def test_build_parser_defaults():
    parser = cli.build_parser()
    args = parser.parse_args(["https://youtu.be/x"])
    assert args.url == "https://youtu.be/x"
    assert args.output_dir == "."
    assert args.quality == "192"
    assert args.filename_template == "%(title)s.%(ext)s"


def test_build_parser_custom_flags():
    parser = cli.build_parser()
    args = parser.parse_args([
        "https://youtu.be/x",
        "-o", "out",
        "-q", "320",
        "--filename-template", "%(id)s.%(ext)s",
    ])
    assert args.output_dir == "out"
    assert args.quality == "320"
    assert args.filename_template == "%(id)s.%(ext)s"


def test_main_returns_nonzero_and_prints_error_when_ffmpeg_missing(monkeypatch, capsys):
    def fake_ensure_ffmpeg():
        raise cli.FfmpegNotFoundError("ffmpeg not found on PATH.")

    monkeypatch.setattr(cli, "ensure_ffmpeg", fake_ensure_ffmpeg)

    rc = cli.main(["https://youtu.be/x"])

    assert rc == 1
    captured = capsys.readouterr()
    assert "ffmpeg not found" in captured.err


def test_main_calls_download_with_parsed_options(monkeypatch):
    monkeypatch.setattr(cli, "ensure_ffmpeg", lambda: None)

    captured = {}

    def fake_download(opts):
        captured["opts"] = opts
        return 0

    monkeypatch.setattr(cli, "download", fake_download)

    rc = cli.main(["https://youtu.be/x", "-o", "out", "-q", "320"])

    assert rc == 0
    assert captured["opts"].url == "https://youtu.be/x"
    assert captured["opts"].output_dir == "out"
    assert captured["opts"].quality == "320"
