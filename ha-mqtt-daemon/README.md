# ha-mqtt-daemon

Home Assistant MQTT daemon for a single peripage printer. Auto-discovers a
BLE printer (P21) over Bluetooth LE and registers itself in Home Assistant
via [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) -
no manual `configuration.yaml` entity setup needed.

Classic Bluetooth printers (A6/A6+/A40/A40+) are supported too, but always
require a configured MAC address - there's no reliable way to auto-discover
*which* classic-Bluetooth device is the printer (unlike BLE, there's no GATT
table to derive characteristic UUIDs from, so scanning wouldn't save more
than typing in the MAC you already needed to pair the device in the first
place).

Image printing is not supported by this daemon - Home Assistant's MQTT
integration has no native "attach an image and print it" entity.

## Install

```
pip install -r requirements-ha.txt
pip install -r requirements-ble.txt      # if PRINTER_TRANSPORT=ble
pip install -r requirements-classic.txt  # if PRINTER_TRANSPORT=classic
```

## Run

```
PRINTER_TYPE=P21 PRINTER_TRANSPORT=ble MQTT_HOST=localhost python -m ha-mqtt-daemon
```

If `PRINTER_BLE_ADDRESS`/`PRINTER_BLE_WRITE_UUID` are not set, the daemon
scans for a nearby BLE device whose advertised name contains
`PRINTER_BLE_NAME_FILTER` (default `PPG` - matches the `PPG_P21_XXXX`-style
name P21 units actually advertise; older/other units may advertise as
`PeriPage+XXXX` instead, so adjust the filter if yours doesn't match) and
auto-picks GATT write/notify characteristics. If that's ambiguous or wrong
on your setup, run:

```
python -m peripage.transport.ble_discover scan
python -m peripage.transport.ble_discover services <address>
```

and pin `PRINTER_BLE_ADDRESS`/`PRINTER_BLE_WRITE_UUID`/`PRINTER_BLE_NOTIFY_UUID` explicitly.

## Install as a service (systemd - recommended)

This is a Linux-only daemon: BLE goes through `bleak`, which on Linux talks to
the printer via BlueZ over D-Bus - that stack (and this install method) is
Linux-specific.

One-liner (no clone needed - the script fetches the repo itself):

```
curl -fsSL https://raw.githubusercontent.com/mdarvanaghi/peripage-python/main/ha-mqtt-daemon/install.sh | sudo bash
```

Already have a checkout? The same script detects that and skips the download:

```
sudo ./ha-mqtt-daemon/install.sh
```

This sets up a venv at `/opt/peripage-python/.venv`, installs deps (BLE by
default; pass `--with-classic` too if you need A6/A6+/A40/A40+), creates a
`peripage` service user with Bluetooth access, and installs+enables the
systemd unit. See `--help` for `--install-dir`/`--user` overrides. It's safe
to re-run (re-running won't re-prompt or touch an existing env file).

On a first-time install, if there's no `peripage-ha.env` yet and you're
running this from a real terminal, it **prompts you for the handful of
settings that need a decision** (printer type, MAC/BLE address, MQTT broker
host/port/credentials, concentration) and writes them straight into
`peripage-ha.env` - everything else keeps its default from
`peripage-ha.env.example`. Once the resulting config actually validates
(checked with the daemon's own config loader, not just "non-empty"), **the
service starts automatically** - no separate "now start it" step.

For BLE printers (P21), the installer also offers to **auto-discover the
address and GATT write/notify UUIDs right there during install** (default
Y - it'll ask you to power the printer on first, then connects once to read
its GATT table). If that succeeds, all three get pinned into
`peripage-ha.env` up front, so the daemon never needs to scan-and-connect
for discovery again on future restarts - it just uses the pinned values
directly. This also front-loads the riskiest part of BLE setup (the very
first programmatic connect to a never-before-paired device, which is where
BlueZ's `br-connection-profile-unavailable` quirk tends to show up) into a
one-shot interactive step where a failure is immediately visible, instead of
a systemd crash-loop. If discovery fails or you decline it, the daemon falls
back to auto-discovering at startup as before (or you can fill in
`PRINTER_BLE_ADDRESS`/`PRINTER_BLE_WRITE_UUID`/`PRINTER_BLE_NOTIFY_UUID`
manually afterwards).

No terminal attached (e.g. piped from something that isn't an interactive
shell), or you'd rather configure it yourself? Pass `--non-interactive` and
it leaves `peripage-ha.env` at the example's blanks:
```
curl -fsSL .../install.sh | sudo bash -s -- --non-interactive
$EDITOR /opt/peripage-python/ha-mqtt-daemon/peripage-ha.env   # PRINTER_TYPE is required
sudo systemctl start peripage-ha
```
(the installer only skips the auto-start when the config doesn't validate -
it'll tell you which case you're in either way)
```
journalctl -u peripage-ha -f
```

<details>
<summary>Equivalent manual steps (what the script does)</summary>

1. Set up a venv and install deps:
   ```
   sudo mkdir -p /opt/peripage-python && sudo chown $USER /opt/peripage-python
   git clone <this repo> /opt/peripage-python   # or copy the checkout there
   cd /opt/peripage-python
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt -r requirements-ha.txt
   .venv/bin/pip install -r requirements-ble.txt      # if PRINTER_TRANSPORT=ble
   .venv/bin/pip install -r requirements-classic.txt  # if PRINTER_TRANSPORT=classic
   ```
2. Configure:
   ```
   cp ha-mqtt-daemon/peripage-ha.env.example ha-mqtt-daemon/peripage-ha.env
   $EDITOR ha-mqtt-daemon/peripage-ha.env
   ```
3. Create a dedicated user and give it Bluetooth access:
   ```
   sudo useradd -r -G bluetooth peripage
   sudo chown -R peripage:peripage /opt/peripage-python
   ```
4. Install and start the unit:
   ```
   sudo cp ha-mqtt-daemon/peripage-ha.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now peripage-ha
   ```
5. Check it's running:
   ```
   sudo systemctl status peripage-ha
   journalctl -u peripage-ha -f
   ```
</details>

## Docker (secondary, BLE caveats)

Docker is *not* the recommended path for BLE printers. BlueZ/`bleak` needs
direct access to the host's D-Bus and Bluetooth adapter, which in practice
means `network_mode: host` (the container isn't network-isolated - MQTT
ports etc. are whatever the host uses, not remapped) plus bind-mounting
`/var/run/dbus`. That defeats most of the point of containerizing, and the
container's BlueZ client library still has to be compatible with whatever
`bluetoothd` version is actually running on the host (they talk over
D-Bus) - version mismatches are a known source of BLE discovery silently
failing or hanging *only* inside the container. If that happens, check the
host/container BlueZ versions first before assuming it's a code bug.

Prefer the systemd install above for BLE. Use Docker if you already run a
docker-based host setup and accept the above; classic-Bluetooth-only setups
have an easier time here since PyBluez doesn't need D-Bus the same way (it
still needs `--network host` to reach the HCI socket, though).

The default image (`ha-mqtt-daemon/Dockerfile`) does not install
`requirements-classic.txt` (PyBluez) - add it to the `pip install` line in
the Dockerfile if you need classic-Bluetooth support; PyBluez pulls in its
own native-extension build requirements.

```
cp ha-mqtt-daemon/peripage-ha.env.example ha-mqtt-daemon/peripage-ha.env
$EDITOR ha-mqtt-daemon/peripage-ha.env
cd ha-mqtt-daemon
docker compose up -d --build
docker compose logs -f
```

## Configuration (environment variables)

| Variable | Default | Notes |
| --- | --- | --- |
| `MQTT_HOST` | `localhost` | |
| `MQTT_PORT` | `1883` | |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | unset | |
| `MQTT_TLS` | `false` | |
| `MQTT_CLIENT_ID` | `peripage_<node_id>` | |
| `HA_DISCOVERY_PREFIX` | `homeassistant` | |
| `HA_NODE_ID` | derived from address/MAC/type | |
| `HA_DEVICE_NAME` | `Peripage <type>` | |
| `PRINTER_TYPE` | *(required)* | One of `peripage.PrinterType.names()`, e.g. `P21`, `A6p` |
| `PRINTER_TRANSPORT` | `ble` | `classic` or `ble` |
| `PRINTER_CONCENTRATION` | `0` | `0`-`2` |
| `PRINTER_MAC` | unset | required for `classic` |
| `PRINTER_TIMEOUT` | `10.0` | seconds |
| `PRINTER_BLE_ADDRESS` | unset | pins BLE address, skips scan |
| `PRINTER_BLE_NAME_FILTER` | `PPG` | substring match during scan (case-insensitive) |
| `PRINTER_BLE_SCAN_TIMEOUT` | `5.0` | seconds |
| `PRINTER_BLE_WRITE_UUID` / `PRINTER_BLE_NOTIFY_UUID` | unset | pins GATT characteristics, skips auto-pick |
| `PRINTER_BLE_PREFER_FAST_WRITE` | `false` | |
| `PRINTER_BLE_WRITE_DELAY` | `0.0` | seconds |
| `PING_INTERVAL` / `EVENT_INTERVAL` / `OFFLINE_INTERVAL` / `STARTUP_INTERVAL` / `GUARD_PING_INTERVAL` | see `print_service.PrintService` | passed straight through |
| `PRINT_TEXT_FONT_SIZE` | `32` | printers with no onboard font only (P21) |
| `PRINT_TEXT_ALIGN` | `left` | `left`/`center`/`right` |
| `PRINT_BREAK_SIZE` | `100` | paper feed after each print job |
| `BATTERY_POLL_INTERVAL` | `300.0` | seconds between battery sensor updates |
| `DISCOVERY_RETRY_ATTEMPTS` / `DISCOVERY_RETRY_BACKOFF` | `5` / `5.0` | retries on transient discovery failure at startup |

## Entities

- **Print text** (`text` entity) - send text to be printed.
- **Battery** (`sensor` entity) - battery percentage.
- **Feed** (`button` entity) - feed some blank paper (handy for testing the connection).

All three share one HA device card and use the standard
`availability_topic`/LWT mechanism to grey out when the daemon or MQTT
connection drops - there is no separate "online" entity. Exact entity IDs
(e.g. `text.print_text` vs `text.peripage_p21_print_text`) depend on how HA
slugifies the name on first discovery, particularly if you run more than one
of these daemons - check the device page (next section) rather than assuming.

## Adding the printer to Home Assistant

This daemon relies entirely on HA's [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) -
there's no manual entity YAML to write. Once it's running and talking to the
right broker, the printer just appears.

**1. Prerequisite: HA's MQTT integration must already be set up**, pointed at
the *same broker* this daemon uses (`MQTT_HOST`/`MQTT_PORT` in your
`peripage-ha.env`). If it isn't yet: Home Assistant → **Settings → Devices &
Services → Add Integration → MQTT**, enter your broker's host/port/credentials.
Discovery is on by default with prefix `homeassistant`, matching this
daemon's default `HA_DISCOVERY_PREFIX` - if you changed one, change the other
to match.

**2. Start the daemon** (see Install sections above) and confirm it actually
connected:
```
journalctl -u peripage-ha -f
```
You should see it connect to MQTT and, if using BLE auto-discovery, log which
device it picked. If `PRINTER_TYPE`/`PRINTER_MAC` (classic) aren't set yet,
it'll fail fast with a clear error - fill in `peripage-ha.env` and restart:
```
sudo systemctl restart peripage-ha
```

**3. Check Home Assistant** - within a few seconds, go to **Settings →
Devices & Services → Devices** and look for a device named after
`HA_DEVICE_NAME` (default `Peripage <type>`, e.g. "Peripage P21"). Open it -
you should see the three entities (Print text, Battery, Feed) listed, all
showing as available (not greyed out) as soon as the daemon is running and
connected to MQTT - see point 6 below for what availability does and
doesn't tell you about the printer itself.

If the device doesn't show up: confirm HA's MQTT integration is connected
(same Settings → Devices & Services page, check the MQTT integration's own
status), and that the daemon's logs show a successful MQTT connect. You can
also watch the discovery messages arrive directly, from any machine that can
reach the broker:
```
mosquitto_sub -h <broker> -t 'homeassistant/#' -v
```
(retained messages replay immediately on subscribe, so you'll see them even
if the daemon started earlier).

**4. Try it** - open the device page and click into **Print text**. Typing a
value and pressing enter sends it straight to the printer. Click **Feed** to
feed some blank paper. **Battery** updates every `BATTERY_POLL_INTERVAL`
seconds (default 300s/5min) - don't expect it to jump immediately after
startup.

**5. Automate it** - once you know the entity ID (from the device page, or
**Developer Tools → States**), call it like any other `text`/`button`
entity, e.g. an automation action:
```yaml
action: text.set_value
target:
  entity_id: text.print_text   # substitute your actual entity id
data:
  value: "Good morning!"
```
or from a script/automation calling `button.press` on the feed entity the
same way.

**6. If something's greyed out** - the `availability_topic`/LWT mechanism
reflects whether the *daemon process* is running and connected to MQTT (via
its LWT + a clean-shutdown "offline" publish). It does **not** currently
reflect whether the printer itself is connected - `PrintService` handles
printer reconnects internally (with its own backoff) and the entities stay
"available" throughout, even while it's retrying. If prints aren't going
through but nothing's greyed out, check `journalctl -u peripage-ha` for
printer-side connection/reconnect messages - that's the only place printer
health currently surfaces.
