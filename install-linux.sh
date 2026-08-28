#!/usr/bin/env bash
#
# yt2y1 installer for Debian/Ubuntu-based Linux (apt)
#
# Run this with:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-linux.sh)"
#
# Not "curl ... | bash": this script runs apt, which is long-running and
# shares this shell's stdin -- piping the script straight into bash can
# desync bash's own read of the piped script against apt reading from
# the same stdin, corrupting execution partway through (seen for real
# with install-macos.sh's equivalent apt/brew step). Command
# substitution downloads the whole script into a string first, so
# there's no live pipe left for anything to race against.
#
# It installs Python, git, ffmpeg and chromaprint via apt if any are
# missing, clones (or updates) yt2y1 into ~/yt2y1, installs both tools
# into one dedicated virtual environment shared between them -- so
# y1sync's "Download from YouTube" menu option can still import yt2mp3,
# and so this doesn't run into newer Debian/Ubuntu's refusal to "pip
# install" outside a venv at all (PEP 668) -- symlinks y1sync and
# yt2mp3 onto your PATH, walks you through the free AcoustID key, and
# finishes with `y1sync doctor` so you can see everything is actually
# ready.
#
# apt-only by design, the same way install-windows.ps1 is winget-only:
# other package managers aren't covered here. See README.md's manual
# steps if apt isn't what your system uses.
#
# Safe to run more than once -- each step is skipped if it's already
# done.

set -euo pipefail

write_step() {
    printf '\n\033[36m==> %s\033[0m\n' "$1"
}

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "\033[32myt2y1 installer\033[0m"
echo "Downloads music from YouTube and gets it onto an Innioasis Y1 player."

# --- 0. apt itself -------------------------------------------------------

if ! has_cmd apt-get; then
    echo ""
    echo "This installer supports Debian/Ubuntu-based systems (apt) only." >&2
    echo "For other distros, follow the manual install steps in README.md:" >&2
    echo "  https://github.com/hozemigel/yt2y1#what-you-need-before-you-start" >&2
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# --- 1-4. Python, git, ffmpeg, chromaprint --------------------------------

write_step "Checking system packages..."

apt_missing=()
has_cmd python3 || apt_missing+=("python3")

# python3-venv is a separate apt package on Debian/Ubuntu even though venv
# is part of the standard library -- "python3 -m venv" fails at creation
# time without it (not at --help time), so this actually creates and
# discards a throwaway venv rather than trusting a flag that would report
# a false "present" on a broken install.
venv_probe_dir="$(mktemp -d)"
if python3 -m venv "$venv_probe_dir/probe" >/dev/null 2>&1; then
    venv_ok=true
else
    venv_ok=false
fi
rm -rf "$venv_probe_dir"
[ "$venv_ok" = true ] || apt_missing+=("python3-venv")

has_cmd git    || apt_missing+=("git")
has_cmd ffmpeg || apt_missing+=("ffmpeg")
# fpcalc is chromaprint's fingerprinting tool; the package that ships it
# on Debian/Ubuntu is named after the tools, not the library.
has_cmd fpcalc || apt_missing+=("libchromaprint-tools")

if [ "${#apt_missing[@]}" -eq 0 ]; then
    echo "  Already installed, skipping."
else
    echo "  Installing: ${apt_missing[*]}"
    $SUDO apt-get update
    $SUDO apt-get install -y "${apt_missing[@]}"
fi

# --- 5. Clone or update yt2y1 --------------------------------------------

write_step "Getting yt2y1..."

REPO_DIR="$HOME/yt2y1"
if [ -d "$REPO_DIR/.git" ]; then
    echo "  Already cloned at $REPO_DIR, pulling the latest..."
    git -C "$REPO_DIR" pull
else
    echo "  Cloning into $REPO_DIR..."
    git clone https://github.com/hozemigel/yt2y1 "$REPO_DIR"
fi

# --- 6. Install both tools into one shared venv --------------------------

write_step "Installing yt2mp3 and y1sync..."

VENV_DIR="$HOME/.local/share/yt2y1/venv"
if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment already exists at $VENV_DIR."
else
    echo "  Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install "$REPO_DIR/yt2mp3" "$REPO_DIR/y1sync"

# --- 7. Put y1sync and yt2mp3 on PATH -------------------------------------

write_step "Adding y1sync and yt2mp3 to your PATH..."

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/y1sync" "$BIN_DIR/y1sync"
ln -sf "$VENV_DIR/bin/yt2mp3" "$BIN_DIR/yt2mp3"

# Makes the two commands usable for the rest of *this* script, without
# waiting for a new shell.
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) export PATH="$BIN_DIR:$PATH" ;;
esac

# Persists it for future terminals. ~/.local/bin is already on PATH out
# of the box on most current distros, so this usually finds nothing to
# do; each rc file is guarded independently so a rerun never duplicates
# the line.
for rc in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc"; do
    [ -f "$rc" ] || continue
    if ! grep -qF "$BIN_DIR" "$rc" 2>/dev/null; then
        printf '\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$rc"
    fi
done

# --- 8. AcoustID key -------------------------------------------------------

write_step "Setting up your free AcoustID key..."

CONFIG_FILE="$HOME/.config/y1sync/config.toml"
has_key=false
if [ -f "$CONFIG_FILE" ] && grep -Eq 'acoustid_key[[:space:]]*=[[:space:]]*"[^"]+"' "$CONFIG_FILE"; then
    has_key=true
fi

if [ "$has_key" = true ]; then
    echo "  Already configured, skipping."
else
    echo "This is what lets y1sync identify tracks accurately instead of guessing"
    echo "from filenames. Opening the signup page in your browser now."
    echo ""
    echo -e "\033[33mOn that page: log in (a Google or GitHub account works), fill in a Name\033[0m"
    echo -e "\033[33mand Version for the form, submit, then copy the API key it shows you.\033[0m"
    echo ""

    if has_cmd xdg-open; then
        xdg-open "https://acoustid.org/new-application" >/dev/null 2>&1 &
    else
        # No desktop environment (a server, a container, WSL without a
        # browser) -- Windows always has a default browser to hand off
        # to, this doesn't, so it's a URL to open yourself instead.
        echo "Open this in a browser: https://acoustid.org/new-application"
    fi

    key=""
    while [ -z "$key" ]; do
        # Explicitly from /dev/tty, not plain stdin: kept as a defensive
        # habit even though the documented bash -c "$(curl ...)" invocation
        # above already leaves stdin free -- a bare "read" here would
        # misbehave the same way the apt/brew step above did if this ever
        # runs under a plain "curl ... | bash" pipe instead.
        read -r -p "Paste your AcoustID application key here: " key < /dev/tty
    done

    # Routed through y1sync's own save_config() rather than writing the
    # file directly: that would blank the whole file, discarding
    # music_folder if it had already been set. save_config() reads the
    # existing file back first and only overwrites acoustid_key. The key
    # travels via an environment variable, not string interpolation into
    # the Python command, since it's pasted from a web page and may
    # contain characters that would need careful escaping otherwise.
    Y1SYNC_ACOUSTID_KEY="$key" "$VENV_DIR/bin/python" -c '
import os
from y1sync.config import Config, save_config
save_config(Config(acoustid_key=os.environ["Y1SYNC_ACOUSTID_KEY"]))
'
    echo "Saved to $CONFIG_FILE"
fi

# --- 9. Confirm everything is ready ---------------------------------------

write_step "Checking everything is ready..."
y1sync doctor

echo ""
echo -e "\033[32mAll done. Connect your Y1 over USB, then run:\033[0m"
echo ""
echo -e "\033[32m  y1sync\033[0m"
echo ""
