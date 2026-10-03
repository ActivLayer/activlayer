#!/bin/sh

set -eu

PROJECT_URL="https://github.com/ActivLayer/activlayer"
DEFAULT_SOURCE="$PROJECT_URL/archive/refs/heads/community-edition.zip"
SOURCE="${ACTIVLAYER_SOURCE:-$DEFAULT_SOURCE}"
INSTALL_ROOT="${ACTIVLAYER_INSTALL_ROOT:-$HOME/.local/share/activlayer}"
BIN_DIR="${ACTIVLAYER_BIN_DIR:-$HOME/.local/bin}"
PYTHON="${ACTIVLAYER_PYTHON:-python3}"

fail() {
    printf 'ActivLayer installation failed: %s\n' "$1" >&2
    exit 1
}

command -v "$PYTHON" >/dev/null 2>&1 || fail "Python 3.11 or newer is required."

"$PYTHON" -c '
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ActivLayer requires Python 3.11 or newer.")
' || fail "Python 3.11 or newer is required."

case "$INSTALL_ROOT" in
    ""|/|"$HOME") fail "Refusing unsafe installation directory: $INSTALL_ROOT" ;;
esac

printf 'Installing ActivLayer Community Edition...\n'
mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [ ! -x "$INSTALL_ROOT/venv/bin/python" ]; then
    "$PYTHON" -m venv "$INSTALL_ROOT/venv" || fail "Could not create the isolated environment."
fi

"$INSTALL_ROOT/venv/bin/python" -m pip install \
    --disable-pip-version-check \
    --quiet \
    --upgrade \
    "$SOURCE" || fail "Package installation failed."

"$INSTALL_ROOT/venv/bin/activlayer" --version >/dev/null || fail "Installed command is not healthy."
ln -sf "$INSTALL_ROOT/venv/bin/activlayer" "$BIN_DIR/activlayer"

case ":$PATH:" in
    *":$BIN_DIR:"*)
        printf '\nActivLayer is ready. Run:\n  activlayer --help\n'
        ;;
    *)
        case "${SHELL:-}" in
            */zsh) PROFILE="$HOME/.zprofile" ;;
            */bash)
                if [ -f "$HOME/.bash_profile" ]; then
                    PROFILE="$HOME/.bash_profile"
                else
                    PROFILE="$HOME/.profile"
                fi
                ;;
            *) PROFILE="$HOME/.profile" ;;
        esac
        PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\""
        if [ ! -f "$PROFILE" ] || ! grep -F "$PATH_LINE" "$PROFILE" >/dev/null 2>&1; then
            printf '\n%s\n' "$PATH_LINE" >> "$PROFILE"
        fi
        printf '\nActivLayer is installed. Open a new terminal, then run:\n  activlayer --help\n'
        ;;
esac
