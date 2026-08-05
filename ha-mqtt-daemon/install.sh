#!/usr/bin/env bash
# Installs ha-mqtt-daemon as a systemd service. Linux only (BLE needs BlueZ).
#
# Usage (from a local checkout):
#   sudo ./ha-mqtt-daemon/install.sh [--install-dir DIR] [--user NAME] \
#       [--with-classic] [--no-ble] [--repo URL] [--ref REF]
#
# Usage (no clone needed - fetches the repo itself):
#   curl -fsSL https://raw.githubusercontent.com/mdarvanaghi/peripage-python/main/ha-mqtt-daemon/install.sh | sudo bash
#
# --repo/--ref (or REPO_URL/REPO_REF env vars) override which repo/branch is
# fetched when there's no local checkout to install from. Flags win over env
# vars. To pass flags through a curl pipe, use `bash -s --`, e.g.:
#   curl -fsSL .../install.sh | sudo bash -s -- --ref feat/ble-support
#
# Idempotent: safe to re-run (won't overwrite an existing env file, recreates
# the venv/unit file each time).

set -euo pipefail

INSTALL_DIR="/opt/peripage-python"
SERVICE_USER="peripage"
WITH_BLE=1
WITH_CLASSIC=0
REPO_URL="${REPO_URL:-https://github.com/mdarvanaghi/peripage-python}"
REPO_REF="${REPO_REF:-main}"

# Set (only) when we downloaded a tarball ourselves - cleaned up on exit.
TARBALL_TMP_DIR=""

cleanup() {
    if [ -n "$TARBALL_TMP_DIR" ] && [ -d "$TARBALL_TMP_DIR" ]; then
        echo "==> Cleaning up temporary files ($TARBALL_TMP_DIR)"
        rm -rf "$TARBALL_TMP_DIR"
    fi
}
trap cleanup EXIT

usage() {
    grep '^#' "$0" | sed -e 's/^#//' -e 's/^ //'
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --user) SERVICE_USER="$2"; shift 2 ;;
        --with-classic) WITH_CLASSIC=1; shift ;;
        --no-ble) WITH_BLE=0; shift ;;
        --repo) REPO_URL="$2"; shift 2 ;;
        --ref) REPO_REF="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Must be run as root (sudo)." >&2
    exit 1
fi

# Both functions below set $REPO_DIR (and fetch_repo_tarball also sets
# $TARBALL_TMP_DIR) directly as globals rather than via `echo`+command
# substitution - command substitution runs in a subshell, and a subshell's
# variable assignments don't propagate back to the parent shell, which would
# silently break the cleanup trap (it reads $TARBALL_TMP_DIR from the main
# shell) and leak the temp dir on every curl-piped run.

fetch_repo_tarball() {
    local tmp_dir tarball_url
    tmp_dir="$(mktemp -d)"
    tarball_url="${REPO_URL}/archive/${REPO_REF}.tar.gz"
    echo "==> No local checkout found - fetching $tarball_url" >&2
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$tarball_url" | tar xz -C "$tmp_dir" --strip-components=1
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$tarball_url" | tar xz -C "$tmp_dir" --strip-components=1
    else
        echo "Need curl or wget to fetch the repo." >&2
        exit 1
    fi
    TARBALL_TMP_DIR="$tmp_dir"
    REPO_DIR="$tmp_dir"
}

resolve_repo_dir() {
    local script_dir
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        if [ -f "$script_dir/requirements.txt" ] && [ -d "$script_dir/peripage" ]; then
            echo "==> Running from local checkout at $script_dir" >&2
            REPO_DIR="$script_dir"
            return
        fi
    fi
    fetch_repo_tarball
}

REPO_DIR=""
resolve_repo_dir

echo "==> Installing from $REPO_DIR to $INSTALL_DIR"

if [ "$REPO_DIR" != "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude '.git' --exclude '.venv' --exclude '__pycache__' "$REPO_DIR"/ "$INSTALL_DIR"/
fi

echo "==> Creating venv"
python3 -m venv "$INSTALL_DIR/.venv"
PIP="$INSTALL_DIR/.venv/bin/pip"

REQ_FILES=(-r "$INSTALL_DIR/requirements.txt" -r "$INSTALL_DIR/requirements-ha.txt")
[ "$WITH_BLE" -eq 1 ] && REQ_FILES+=(-r "$INSTALL_DIR/requirements-ble.txt")
[ "$WITH_CLASSIC" -eq 1 ] && REQ_FILES+=(-r "$INSTALL_DIR/requirements-classic.txt")

echo "==> Installing dependencies"
"$PIP" install "${REQ_FILES[@]}"

ENV_FILE="$INSTALL_DIR/ha-mqtt-daemon/peripage-ha.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "==> Creating $ENV_FILE from example (edit this before starting the service)"
    cp "$INSTALL_DIR/ha-mqtt-daemon/peripage-ha.env.example" "$ENV_FILE"
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "==> Creating service user $SERVICE_USER"
    useradd -r -G bluetooth "$SERVICE_USER"
else
    usermod -aG bluetooth "$SERVICE_USER"
fi

echo "==> Setting ownership"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

UNIT_PATH="/etc/systemd/system/peripage-ha.service"
echo "==> Writing $UNIT_PATH"
sed \
    -e "s#/opt/peripage-python#${INSTALL_DIR}#g" \
    -e "s#^User=peripage#User=${SERVICE_USER}#" \
    "$INSTALL_DIR/ha-mqtt-daemon/peripage-ha.service" > "$UNIT_PATH"

systemctl daemon-reload
systemctl enable peripage-ha

echo
echo "==> Done. Before starting the service:"
echo "      edit $ENV_FILE (PRINTER_TYPE is required, PRINTER_MAC too if classic)"
echo "    then:"
echo "      systemctl start peripage-ha"
echo "      journalctl -u peripage-ha -f"
