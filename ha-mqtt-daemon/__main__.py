# peripage-python - Home Assistant MQTT daemon
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Home Assistant MQTT daemon for a single peripage printer.

Run with:
    python -m ha-mqtt-daemon

Configuration is entirely via environment variables - see README.md in this
directory (or config.py's `Config.from_env`) for the full list.
"""

import logging
import os
import signal
import sys
import threading
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
_PRINT_SERVER_DIR = os.path.join(_REPO_ROOT, 'print-server')

for path in (_THIS_DIR, _PRINT_SERVER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import config as config_module
import discovery
import mqtt_bridge
import print_service

logger = logging.getLogger('ha-mqtt-daemon')


def _connect_transport_with_retry(cfg: config_module.Config):
    attempt = 0
    while True:
        attempt += 1
        try:
            return discovery.build_transport(cfg)
        except discovery.DiscoveryError as e:
            if attempt >= cfg.discovery_retry_attempts:
                raise
            logger.warning(
                'Printer discovery failed (attempt %d/%d): %s - retrying in %.1fs',
                attempt, cfg.discovery_retry_attempts, e, cfg.discovery_retry_backoff,
            )
            time.sleep(cfg.discovery_retry_backoff)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    try:
        cfg = config_module.Config.from_env()
    except config_module.ConfigError as e:
        logger.error('Configuration error: %s', e)
        sys.exit(1)

    transport = _connect_transport_with_retry(cfg)

    from peripage import PrinterType

    service = print_service.PrintService(
        ping_interval=cfg.ping_interval,
        event_interval=cfg.event_interval,
        offline_interval=cfg.offline_interval,
        startup_interval=cfg.startup_interval,
        guard_ping_interval=cfg.guard_ping_interval,
    )
    service.start(transport, PrinterType[cfg.printer_type], concentration=cfg.concentration)

    import paho.mqtt.client as mqtt

    client = mqtt.Client(client_id=cfg.mqtt_client_id)
    if cfg.mqtt_username:
        client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
    if cfg.mqtt_tls:
        client.tls_set()

    bridge = mqtt_bridge.HaMqttBridge(cfg, service, client)

    client.connect(cfg.mqtt_host, cfg.mqtt_port)
    client.loop_start()

    battery_timer = print_service.Repeat(
        cfg.battery_poll_interval,
        lambda: service.add_print_handler(lambda p: bridge.publish_battery(p.getDeviceBattery())),
    )
    battery_timer.start()

    stop_event = threading.Event()

    def _shutdown(*_args):
        logger.info('Shutting down ...')
        try:
            bridge.publish_offline()
        except Exception:
            pass
        battery_timer.stop()
        service.stop()
        client.loop_stop()
        client.disconnect()
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info('Daemon started (node_id=%s, printer_type=%s, transport=%s)',
                cfg.ha_node_id, cfg.printer_type, cfg.transport_kind)

    stop_event.wait()


if __name__ == '__main__':
    main()
