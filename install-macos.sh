#!/usr/bin/env bash
#
# yt2y1 installer for macOS (Homebrew)
#
# Run this with:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-macos.sh)"
#
# Not "curl ... | bash": this script runs Homebrew, which is
# long-running and shares this shell's stdin -- piping the script
# straight into bash can desync bash's own read of the piped script
# against brew reading from the same stdin, corrupting execution
# partway through (this is exactly what happened on a real run: the
# script's own unexecuted source started leaking into the terminal
# output right after "brew install"). Command substitution downloads
# the whole script into a string first, so there's no live pipe left
# for anything to race against.
#
# It installs Homebrew itself if missing, then Python, git, ffmpeg and
# chromaprint via Homebrew if any of those are missing, clones (or
# updates) yt2y1 into ~/yt2y1, installs both tools into one dedicated
# virtual environment shared between them -- so y1sync's "Download from
# YouTube" menu option can still import yt2mp3, and so this doesn't run
# into Homebrew's Python refusing a bare "pip install" outside a venv
# (PEP 668) -- symlinks y1sync and yt2mp3 onto your PATH, walks you
# through the free AcoustID key, and finishes with `y1sync doctor` so
# you can see everything is actually ready.
#
# Homebrew-only by design, the same way install-windows.ps1 is
# winget-only and install-linux.sh is apt-only: it's what the README
# already documents for macOS. If you use MacPorts or prefer installing
# by hand, the manual steps in README.md work fine instead.
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

# Adds a line to every shell startup file that exists, unless it's
# already there -- covers zsh (the default since Catalina) and bash
# (both the login-shell ~/.bash_profile macOS's Terminal.app actually
# reads, and plain ~/.bashrc for anyone who sources it themselves),
# without ever duplicating the line on a rerun.
ensure_line_in_rc() {
    local line="$1"
    local rc
    for rc in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
        [ -f "$rc" ] || continue
        if ! grep -qF "$line" "$rc" 2>/dev/null; then
            printf '\n%s\n' "$line" >> "$rc"
        fi
    done
}

echo -e "\033[32myt2y1 installer\033[0m"
echo "Downloads music from YouTube and gets it onto an Innioasis Y1 player."

# --- 0. Homebrew itself ---------------------------------------------------

if has_cmd brew; then
    write_step "Homebrew already installed, skipping."
    BREW_BIN="$(command -v brew)"
else
    write_step "Homebrew not found -- installing it first..."
    # The exact command Homebrew's own site (brew.sh) documents.
    # NONINTERACTIVE skips its own confirmation prompt; it may still
    # pop up Apple's native dialog to install Command Line Tools if
    # those aren't present yet -- nothing short of having them
    # preinstalled avoids that, on any Mac.
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Homebrew lands in different places depending on the Mac's CPU
    # architecture (Apple Silicon vs. Intel), so there's no single path
    # to assume.
    if [ -x /opt/homebrew/bin/brew ]; then
        BREW_BIN=/opt/homebrew/bin/brew
    elif [ -x /usr/local/bin/brew ]; then
        BREW_BIN=/usr/local/bin/brew
    else
        echo "Homebrew's installer finished, but 'brew' wasn't found at" >&2
        echo "either of its usual locations. See https://brew.sh for" >&2
        echo "manual install steps, then run this script again." >&2
        exit 1
    fi

    # Makes 'brew' usable for the rest of *this* script; persisted for
    # future terminals the same way Homebrew's own installer tells you
    # to by hand, so this script doesn't leave you needing to follow up
    # a printed instruction yourself.
    eval "$("$BREW_BIN" shellenv)"
    ensure_line_in_rc "eval \"\$($BREW_BIN shellenv)\""
fi

# --- 1-4. Python, git, ffmpeg, chromaprint --------------------------------

write_step "Checking system packages..."

brew_missing=()
if has_cmd python3 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    :
else
    brew_missing+=("python3")
fi
has_cmd git    || brew_missing+=("git")
has_cmd ffmpeg || brew_missing+=("ffmpeg")
# fpcalc is chromaprint's fingerprinting tool; the formula is named
# after the library, not the tool it ships.
has_cmd fpcalc || brew_missing+=("chromaprint")

if [ "${#brew_missing[@]}" -eq 0 ]; then
    echo "  Already installed, skipping."
else
    echo "  Installing: ${brew_missing[*]}"
    brew install "${brew_missing[@]}"
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
# waiting for a new terminal.
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) export PATH="$BIN_DIR:$PATH" ;;
esac

# Persists it for future terminals. Unlike Homebrew's own bin dir,
# ~/.local/bin isn't put on PATH by anything on a stock Mac, so this
# reliably has something to do the first time.
ensure_line_in_rc "export PATH=\"$BIN_DIR:\$PATH\""

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

    open "https://acoustid.org/new-application"

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
