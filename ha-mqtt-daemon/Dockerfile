# Secondary deployment path - see README.md "Docker (secondary, BLE caveats)"
# before using this. systemd + venv (peripage-ha.service) is the primary,
# more reliable path for BLE printers.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libbluetooth-dev bluez dbus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-ha.txt requirements-ble.txt requirements-classic.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ha.txt -r requirements-ble.txt
# requirements-classic.txt (PyBluez) is intentionally not installed by default -
# only needed for classic-Bluetooth printers (A6/A6+/A40/A40+), and it pulls in
# its own native-extension build requirements. Add
# `-r requirements-classic.txt` to the pip install above if you need it.

COPY peripage/ ./peripage/
COPY print-server/ ./print-server/
COPY ha-mqtt-daemon/ ./ha-mqtt-daemon/

CMD ["python", "-m", "ha-mqtt-daemon"]
