#!/usr/bin/env bash
# Installs ha-mqtt-daemon as a systemd service. Linux only (BLE needs BlueZ).
#
# Usage (from a local checkout):
#   sudo ./ha-mqtt-daemon/install.sh [--install-dir DIR] [--user NAME] \
#       [--with-classic] [--no-ble] [--repo URL] [--ref REF] [--non-interactive]
#
# Usage (no clone needed - fetches the repo itself):
#   curl -fsSL https://raw.githubusercontent.com/mdarvanaghi/peripage-python/main/ha-mqtt-daemon/install.sh | sudo bash
#
# --repo/--ref (or REPO_URL/REPO_REF env vars) override which repo/branch is
# fetched when there's no local checkout to install from. Flags win over env
# vars. To pass flags through a curl pipe, use `bash -s --`, e.g.:
#   curl -fsSL .../install.sh | sudo bash -s -- --ref some-other-branch
#
# On a first-time install (no peripage-ha.env yet) run from a real terminal,
# this prompts for the handful of settings that actually need a human
# decision (printer type/address, MQTT broker) and fills in peripage-ha.env
# from your answers. Everything else keeps the defaults from
# peripage-ha.env.example - edit the file afterwards for anything not asked
# about. Pass --non-interactive (or run with no controlling tty, e.g. from
# CI) to skip prompting and leave the example's blanks for you to fill in
# by hand.
#
# Once peripage-ha.env has everything required (checked with the daemon's
# own config validation, not just "is it non-empty"), the service is
# started automatically - no separate "now start it" step needed.
#
# Idempotent: safe to re-run. Won't overwrite an existing env file (so it
# never re-prompts or clobbers answers from a previous run), reuses the
# existing venv (pip install is a no-op for already-satisfied deps),
# regenerates the unit file and re-applies user/group/ownership each time,
# and restarts the service afterwards if (and only if) it was already
# running - so re-running to pick up a code update doesn't require
# remembering to restart it yourself.

set -euo pipefail

INSTALL_DIR="/opt/peripage-python"
SERVICE_USER="peripage"
WITH_BLE=1
WITH_CLASSIC=0
REPO_URL="${REPO_URL:-https://github.com/mdarvanaghi/peripage-python}"
REPO_REF="${REPO_REF:-main}"
NON_INTERACTIVE=0

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
    # Only the leading header comment block (stops at the first non-#
    # line) - later inline comments in the script body shouldn't leak in.
    sed -n '2,/^[^#]/p' "$0" | sed -e '$d' -e 's/^#//' -e 's/^ //'
    exit 1
}

require_arg() {
    # $1 = flag name (for the error message), $2 = value (possibly unset)
    if [ -z "${2:-}" ]; then
        echo "Missing value for $1" >&2
        usage
    fi
}

while [ $# -gt 0 ]; do
    case "$1" in
        --install-dir) require_arg "$1" "${2:-}"; INSTALL_DIR="$2"; shift 2 ;;
        --user) require_arg "$1" "${2:-}"; SERVICE_USER="$2"; shift 2 ;;
        --with-classic) WITH_CLASSIC=1; shift ;;
        --no-ble) WITH_BLE=0; shift ;;
        --repo) require_arg "$1" "${2:-}"; REPO_URL="$2"; shift 2 ;;
        --ref) require_arg "$1" "${2:-}"; REPO_REF="$2"; shift 2 ;;
        --non-interactive) NON_INTERACTIVE=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

REPO_URL="${REPO_URL%/}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Must be run as root (sudo)." >&2
    exit 1
fi

# Fail fast with a clear message instead of a cryptic error partway through.
missing_tools=()
for tool in python3 rsync sed systemctl getent; do
    command -v "$tool" >/dev/null 2>&1 || missing_tools+=("$tool")
done
if [ "${#missing_tools[@]}" -gt 0 ]; then
    echo "Missing required tool(s): ${missing_tools[*]}" >&2
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
    if [ ! -f "$tmp_dir/requirements.txt" ] || [ ! -d "$tmp_dir/peripage" ]; then
        echo "Fetched archive from $tarball_url doesn't look like the expected repo layout." >&2
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

# Was the service already running before this (re-)install? Decides restart
# vs start at the very end, once we know the resulting config is valid.
was_active=0
if systemctl is-active --quiet peripage-ha 2>/dev/null; then
    was_active=1
fi

echo "==> Creating/updating venv"
python3 -m venv "$INSTALL_DIR/.venv"
PIP="$INSTALL_DIR/.venv/bin/pip"

REQ_FILES=(-r "$INSTALL_DIR/requirements.txt" -r "$INSTALL_DIR/requirements-ha.txt")
[ "$WITH_BLE" -eq 1 ] && REQ_FILES+=(-r "$INSTALL_DIR/requirements-ble.txt")
[ "$WITH_CLASSIC" -eq 1 ] && REQ_FILES+=(-r "$INSTALL_DIR/requirements-classic.txt")

echo "==> Installing dependencies"
"$PIP" install "${REQ_FILES[@]}"

# -- env file + interactive config -----------------------------------------

ENV_FILE="$INSTALL_DIR/ha-mqtt-daemon/peripage-ha.env"
env_file_is_new=0
if [ ! -f "$ENV_FILE" ]; then
    echo "==> Creating $ENV_FILE from example"
    cp "$INSTALL_DIR/ha-mqtt-daemon/peripage-ha.env.example" "$ENV_FILE"
    env_file_is_new=1
else
    echo "==> Keeping existing $ENV_FILE"
fi
# Contains (or will contain) an MQTT password - keep it out of reach of
# other local users regardless of how it was populated.
chmod 600 "$ENV_FILE"

have_tty() {
    [ -r /dev/tty ] && [ -w /dev/tty ]
}

# prompt VAR "question text" ["default"] - reads from /dev/tty explicitly,
# not stdin: when this script is run as `curl ... | sudo bash`, stdin is the
# pipe carrying the script itself, not a terminal - `read` against stdin
# would consume/corrupt the script stream instead of prompting anyone.
prompt() {
    local __var="$1" __question="$2" __default="${3:-}" __answer
    if [ -n "$__default" ]; then
        read -r -p "$__question [$__default]: " __answer < /dev/tty
    else
        read -r -p "$__question: " __answer < /dev/tty
    fi
    printf -v "$__var" '%s' "${__answer:-$__default}"
}

prompt_secret() {
    local __var="$1" __question="$2" __answer
    read -r -s -p "$__question: " __answer < /dev/tty
    echo >&2
    printf -v "$__var" '%s' "$__answer"
}

# set_env_var FILE KEY VALUE - uncomments (if needed) and sets KEY='VALUE' in
# an existing env file, leaving every other line (including other commented
# defaults) untouched. The value is always single-quoted (embedded single
# quotes escaped the standard '\'' way) - both this script's own `source
# "$ENV_FILE"` (in validate_config) and systemd's EnvironmentFile= actually
# run this through shell-style word-splitting, so an unquoted value with a
# space (e.g. the "Peripage P21" device name default) gets parsed as two
# words - the second one then runs as a command ("P21: command not found").
# Single-quoting also blocks $-expansion/command substitution of anything
# a user types in at a prompt (e.g. an MQTT password containing `$` or `` ` ``).
#
# Deliberately pure bash, no awk/sed for the substitution itself: awk's `-v`
# reprocesses backslash escapes in the value it's given, which silently
# mangles the very '\'' escape this function constructs (turns it into
# `'''`, corrupting the quoting it just built) - `printf '%s'` never
# reinterprets its argument, so it's the only safe way to place an
# already-escaped value onto a line.
set_env_var() {
    local file="$1" key="$2" value="$3" escaped quoted
    escaped="${value//"'"/"'\\''"}"
    quoted="'$escaped'"

    local tmp="$file.tmp" line bare found=0
    : > "$tmp"
    while IFS= read -r line || [ -n "$line" ]; do
        bare="${line#\#}"
        case "$bare" in
            "$key="*)
                printf '%s=%s\n' "$key" "$quoted" >> "$tmp"
                found=1
                ;;
            *)
                printf '%s\n' "$line" >> "$tmp"
                ;;
        esac
    done < "$file"
    [ "$found" -eq 1 ] || printf '%s=%s\n' "$key" "$quoted" >> "$tmp"
    mv "$tmp" "$file"
}

if [ "$env_file_is_new" -eq 1 ] && [ "$NON_INTERACTIVE" -eq 0 ] && have_tty; then
    echo
    echo "==> Configuring $ENV_FILE (press Enter to accept the [default])"
    echo

    printer_type="" printer_transport="" mac="" ble_address=""
    mqtt_host="" mqtt_port="" mqtt_user="" mqtt_pass="" device_name="" concentration=""

    while true; do
        prompt printer_type "Printer type - one of A6, A6p, A40, A40p, P21"
        case "$printer_type" in
            A6|A6p|A40|A40p|P21) break ;;
            *) echo "Must be exactly one of: A6, A6p, A40, A40p, P21" >&2 ;;
        esac
    done

    if [ "$printer_type" = "P21" ]; then
        printer_transport="ble"
    else
        printer_transport="classic"
    fi
    echo "==> Transport: $printer_transport (implied by printer type $printer_type)"

    if [ "$printer_transport" = "classic" ]; then
        while true; do
            prompt mac "Printer Bluetooth MAC address (e.g. 00:15:83:15:bc:5f)"
            [ -n "$mac" ] && break
            echo "Required for classic Bluetooth printers." >&2
        done
    else
        prompt ble_address "BLE address (blank = auto-discover by scanning for a nearby 'PPG' device)"
    fi

    prompt mqtt_host "MQTT broker host" "localhost"
    while true; do
        prompt mqtt_port "MQTT broker port" "1883"
        case "$mqtt_port" in
            ''|*[!0-9]*) echo "Must be a number." >&2 ;;
            *) break ;;
        esac
    done
    prompt mqtt_user "MQTT username (blank = none/anonymous)"
    if [ -n "$mqtt_user" ]; then
        prompt_secret mqtt_pass "MQTT password"
    fi

    prompt device_name "Home Assistant device name" "Peripage $printer_type"

    while true; do
        prompt concentration "Print concentration 0 (light) - 2 (dark)" "0"
        case "$concentration" in
            0|1|2) break ;;
            *) echo "Must be 0, 1, or 2." >&2 ;;
        esac
    done

    set_env_var "$ENV_FILE" PRINTER_TYPE "$printer_type"
    set_env_var "$ENV_FILE" PRINTER_TRANSPORT "$printer_transport"
    [ -n "$mac" ] && set_env_var "$ENV_FILE" PRINTER_MAC "$mac"
    [ -n "$ble_address" ] && set_env_var "$ENV_FILE" PRINTER_BLE_ADDRESS "$ble_address"
    set_env_var "$ENV_FILE" MQTT_HOST "$mqtt_host"
    set_env_var "$ENV_FILE" MQTT_PORT "$mqtt_port"
    [ -n "$mqtt_user" ] && set_env_var "$ENV_FILE" MQTT_USERNAME "$mqtt_user"
    [ -n "$mqtt_pass" ] && set_env_var "$ENV_FILE" MQTT_PASSWORD "$mqtt_pass"
    set_env_var "$ENV_FILE" HA_DEVICE_NAME "$device_name"
    set_env_var "$ENV_FILE" PRINTER_CONCENTRATION "$concentration"

    echo "==> Wrote $ENV_FILE"
    echo "    (anything not asked about above keeps its default from peripage-ha.env.example - edit the file for those)"
elif [ "$env_file_is_new" -eq 1 ]; then
    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        echo "==> --non-interactive: leaving $ENV_FILE with its example defaults - fill it in by hand."
    else
        echo "==> No controlling terminal detected - leaving $ENV_FILE with its example defaults - fill it in by hand."
    fi
fi

if getent group bluetooth >/dev/null 2>&1; then
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        echo "==> Creating service user $SERVICE_USER"
        useradd -r -G bluetooth "$SERVICE_USER"
    else
        usermod -aG bluetooth "$SERVICE_USER"
    fi
else
    echo "==> Warning: no 'bluetooth' group found (is bluez installed?) - creating $SERVICE_USER without it" >&2
    id "$SERVICE_USER" >/dev/null 2>&1 || useradd -r "$SERVICE_USER"
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

# -- validate config, then start/restart only if it actually works --------

validate_config() {
    (
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
        "$INSTALL_DIR/.venv/bin/python" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR/ha-mqtt-daemon')
sys.path.insert(0, '$INSTALL_DIR')
import config as config_module
try:
    config_module.Config.from_env()
except config_module.ConfigError as e:
    print(f'Config error: {e}', file=sys.stderr)
    sys.exit(1)
"
    )
}

echo
if validate_config; then
    if [ "$was_active" -eq 1 ]; then
        echo "==> Configuration is valid - restarting the service to apply the update"
        systemctl restart peripage-ha
    else
        echo "==> Configuration is valid - starting the service"
        systemctl start peripage-ha
    fi
    echo "==> Done. journalctl -u peripage-ha -f"
else
    if [ "$was_active" -eq 1 ]; then
        echo "==> Warning: $ENV_FILE failed validation - leaving the already-running service untouched." >&2
    else
        echo "==> Done, but not started: $ENV_FILE isn't fully configured yet."
        echo "      edit $ENV_FILE then:"
        echo "      sudo systemctl start peripage-ha"
    fi
    echo "      journalctl -u peripage-ha -f"
fi
