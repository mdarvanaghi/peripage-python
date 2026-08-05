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
`PRINTER_BLE_NAME_FILTER` (default `PeriPage`) and auto-picks GATT write/notify
characteristics. If that's ambiguous or wrong on your setup, run:

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
`peripage` service user with Bluetooth access, copies `peripage-ha.env.example`
to `peripage-ha.env` if it doesn't already exist, and installs+enables the
systemd unit (without starting it, since the env file still needs editing).
See `--help` for `--install-dir`/`--user` overrides. It's safe to re-run.

Then:
```
$EDITOR /opt/peripage-python/ha-mqtt-daemon/peripage-ha.env   # PRINTER_TYPE is required
sudo systemctl start peripage-ha
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
| `PRINTER_BLE_NAME_FILTER` | `PeriPage` | substring match during scan |
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

- `text.print_text` - send text to be printed.
- `sensor.battery` - battery percentage.
- `button.feed` - feed some blank paper (handy for testing the connection).

All entities share one HA device card and use the standard
`availability_topic`/LWT mechanism to grey out when the daemon or MQTT
connection drops - there is no separate "online" entity.
