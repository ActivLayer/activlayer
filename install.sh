#!/bin/sh

set -eu

PROJECT_URL="https://github.com/ActivLayer/activlayer"
DEFAULT_SOURCE="$PROJECT_URL/archive/refs/heads/community-edition.zip"
SOURCE="${ACTIVLAYER_SOURCE:-$DEFAULT_SOURCE}"
INSTALL_ROOT="${ACTIVLAYER_INSTALL_ROOT:-$HOME/.local/share/activlayer}"
BIN_DIR="${ACTIVLAYER_BIN_DIR:-$HOME/.local/bin}"
PYTHON="${ACTIVLAYER_PYTHON:-python3}"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD=$(printf '\033[1m')
    VIOLET=$(printf '\033[35m')
    CYAN=$(printf '\033[36m')
    GREEN=$(printf '\033[32m')
    DIM=$(printf '\033[2m')
    RESET=$(printf '\033[0m')
else
    BOLD=""
    VIOLET=""
    CYAN=""
    GREEN=""
    DIM=""
    RESET=""
fi

fail() {
    printf '\n%sInstallation failed%s\n  %s\n' "$BOLD" "$RESET" "$1" >&2
    exit 1
}

step() {
    printf '%s%s[%s]%s %s\n' "$CYAN" "$BOLD" "$1" "$RESET" "$2"
}

printf '\n%s%sActivLayer%s %sCommunity Edition installer%s\n\n' \
    "$VIOLET" "$BOLD" "$RESET" "$DIM" "$RESET"

step "1/4" "Checking Python runtime"
command -v "$PYTHON" >/dev/null 2>&1 || fail "Python 3.11 or newer is required."

"$PYTHON" -c '
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ActivLayer requires Python 3.11 or newer.")
' || fail "Python 3.11 or newer is required."

case "$INSTALL_ROOT" in
    ""|/|"$HOME") fail "Refusing unsafe installation directory: $INSTALL_ROOT" ;;
esac

PYTHON_VERSION=$("$PYTHON" -c 'import platform; print(platform.python_version())')
printf '      Python %s · %s\n' "$PYTHON_VERSION" "$PYTHON"

step "2/4" "Preparing isolated environment"
mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [ ! -x "$INSTALL_ROOT/venv/bin/python" ]; then
    "$PYTHON" -m venv "$INSTALL_ROOT/venv" || fail "Could not create the isolated environment."
fi

printf '      %s\n' "$INSTALL_ROOT/venv"

step "3/4" "Downloading and installing ActivLayer"
if [ "${ACTIVLAYER_VERBOSE:-0}" = "1" ]; then
    "$INSTALL_ROOT/venv/bin/python" -m pip install \
        --disable-pip-version-check \
        --upgrade \
        "$SOURCE" || fail "Package installation failed."
else
    "$INSTALL_ROOT/venv/bin/python" -m pip install \
        --disable-pip-version-check \
        --quiet \
        --upgrade \
        "$SOURCE" || fail "Package installation failed. Set ACTIVLAYER_VERBOSE=1 for details."
fi

VERSION_OUTPUT=$("$INSTALL_ROOT/venv/bin/activlayer" --version) || \
    fail "Installed command is not healthy."

step "4/4" "Exposing the activlayer command"
ln -sf "$INSTALL_ROOT/venv/bin/activlayer" "$BIN_DIR/activlayer"

case ":$PATH:" in
    *":$BIN_DIR:"*)
        PATH_NOTE="Ready in this terminal"
        NEXT_COMMAND="activlayer --help"
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
        PATH_NOTE="PATH updated in $PROFILE · open a new terminal once"
        NEXT_COMMAND="activlayer --help"
        ;;
esac

printf '\n%s%s╭──────────────────────────────────────────────────────────╮%s\n' \
    "$GREEN" "$BOLD" "$RESET"
printf '%s%s│  ✓ ActivLayer installed successfully                     │%s\n' \
    "$GREEN" "$BOLD" "$RESET"
printf '%s%s╰──────────────────────────────────────────────────────────╯%s\n' \
    "$GREEN" "$BOLD" "$RESET"
printf '  Version     %s\n' "$VERSION_OUTPUT"
printf '  Command     %s/activlayer\n' "$BIN_DIR"
printf '  Shell       %s\n' "$PATH_NOTE"
printf '\n%sNext:%s %s%s%s\n\n' "$BOLD" "$RESET" "$VIOLET" "$NEXT_COMMAND" "$RESET"
