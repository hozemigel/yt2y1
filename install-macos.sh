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
# It installs Homebrew itself if missing, then Python, git, ffmpeg,
# chromaprint and deno (a JS runtime yt-dlp uses for reliable YouTube
# downloads) via Homebrew if any of those are missing, clones (or
# updates) yt2y1 into ~/yt2y1, installs both tools into one dedicated
# virtual environment shared between them -- so y1sync's "Download from
# YouTube" menu option can still import yt2mp3, and so this doesn't run
# into Homebrew's Python refusing a bare "pip install" outside a venv
# (PEP 668) -- symlinks y1sync and yt2mp3 onto your PATH, and finishes
# with `y1sync doctor` so you can see everything is actually ready.
# Audio fingerprinting needs no key or signup: y1sync ships with its own
# AcoustID lookup key.
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

# --- 4b. deno (JS runtime for reliable YouTube downloads) ----------------
#
# Not required the way the packages above are -- y1sync's readiness check
# doesn't depend on it, and yt2mp3 still works without it. But yt-dlp's
# YouTube extraction is markedly less reliable without a JS runtime
# present (more timeouts, occasional failed downloads). Installed
# separately from brew_missing above so that a failure here is a
# warning, not a reason to abort the whole install the way a failed
# ffmpeg or chromaprint install would be.

write_step "Checking for a JS runtime (deno)..."
if has_cmd deno; then
    echo "  Already installed, skipping."
elif brew install deno; then
    :
else
    echo "  Could not install deno automatically -- YouTube downloads will"
    echo "  still work, just less reliably. See"
    echo "  https://docs.deno.com/runtime/getting_started/installation/"
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

# --- 8. Confirm everything is ready ---------------------------------------

write_step "Checking everything is ready..."
y1sync doctor

echo ""
echo -e "\033[32mAll done. Connect your Y1 over USB, then run:\033[0m"
echo ""
echo -e "\033[32m  y1sync\033[0m"
echo ""
