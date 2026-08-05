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
Env-var driven configuration for the Home Assistant MQTT daemon.

See README.md in this directory for the full list of variables and their
defaults.
"""

import dataclasses
import os
import re
import typing


class ConfigError(Exception):
    """Raised for invalid/missing configuration. Caller should treat this
    as fatal (print message, exit non-zero)."""


def _env(name: str, default: typing.Optional[str] = None) -> typing.Optional[str]:
    return os.environ.get(name, default)


def _env_str(name: str, default: str) -> str:
    return _env(name, default)


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f'{name}={value!r} is not a valid integer')


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise ConfigError(f'{name}={value!r} is not a valid float')


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_optional(name: str) -> typing.Optional[str]:
    value = _env(name)
    return value if value else None


def _slugify(value: str) -> str:
    return re.sub(r'[^a-z0-9_]+', '_', value.lower()).strip('_')


@dataclasses.dataclass
class Config:
    # MQTT
    mqtt_host: str
    mqtt_port: int
    mqtt_username: typing.Optional[str]
    mqtt_password: typing.Optional[str]
    mqtt_tls: bool
    mqtt_client_id: str

    # HA discovery
    ha_discovery_prefix: str
    ha_node_id: str
    ha_device_name: str

    # Printer
    printer_type: str
    transport_kind: str
    concentration: int

    # Classic-only
    mac: typing.Optional[str]
    printer_timeout: float

    # BLE-only
    ble_address: typing.Optional[str]
    ble_name_filter: str
    ble_scan_timeout: float
    ble_write_uuid: typing.Optional[str]
    ble_notify_uuid: typing.Optional[str]
    ble_prefer_fast_write: bool
    ble_write_delay: float

    # PrintService passthrough
    ping_interval: float
    event_interval: float
    offline_interval: float
    startup_interval: float
    guard_ping_interval: typing.Optional[float]

    # Behavior
    font_size: int
    align: str
    break_size: int
    battery_poll_interval: float

    # Discovery retry
    discovery_retry_attempts: int
    discovery_retry_backoff: float

    @staticmethod
    def from_env() -> 'Config':
        import peripage

        printer_type = _env_str('PRINTER_TYPE', '')
        if printer_type not in peripage.PrinterType.names():
            raise ConfigError(
                f'PRINTER_TYPE={printer_type!r} is required and must be one of: '
                f'{", ".join(peripage.PrinterType.names())}'
            )

        transport_kind = _env_str('PRINTER_TRANSPORT', 'ble')
        if transport_kind not in ('classic', 'ble'):
            raise ConfigError(f'PRINTER_TRANSPORT={transport_kind!r} must be "classic" or "ble"')

        mac = _env_optional('PRINTER_MAC')
        if transport_kind == 'classic' and not mac:
            raise ConfigError('PRINTER_MAC is required when PRINTER_TRANSPORT=classic '
                               '(classic Bluetooth has no reliable auto-discovery)')

        ble_address = _env_optional('PRINTER_BLE_ADDRESS')
        ble_write_uuid = _env_optional('PRINTER_BLE_WRITE_UUID')

        node_id_default = _slugify(ble_address or mac or printer_type)
        ha_node_id = _env_str('HA_NODE_ID', node_id_default)

        guard_ping_interval_raw = _env_optional('GUARD_PING_INTERVAL')
        guard_ping_interval = float(guard_ping_interval_raw) if guard_ping_interval_raw else 1.0

        return Config(
            mqtt_host=_env_str('MQTT_HOST', 'localhost'),
            mqtt_port=_env_int('MQTT_PORT', 1883),
            mqtt_username=_env_optional('MQTT_USERNAME'),
            mqtt_password=_env_optional('MQTT_PASSWORD'),
            mqtt_tls=_env_bool('MQTT_TLS', False),
            mqtt_client_id=_env_str('MQTT_CLIENT_ID', f'peripage_{ha_node_id}'),

            ha_discovery_prefix=_env_str('HA_DISCOVERY_PREFIX', 'homeassistant'),
            ha_node_id=ha_node_id,
            ha_device_name=_env_str('HA_DEVICE_NAME', f'Peripage {printer_type}'),

            printer_type=printer_type,
            transport_kind=transport_kind,
            concentration=_env_int('PRINTER_CONCENTRATION', 0),

            mac=mac,
            printer_timeout=_env_float('PRINTER_TIMEOUT', 10.0),

            ble_address=ble_address,
            ble_name_filter=_env_str('PRINTER_BLE_NAME_FILTER', 'PPG'),
            ble_scan_timeout=_env_float('PRINTER_BLE_SCAN_TIMEOUT', 5.0),
            ble_write_uuid=ble_write_uuid,
            ble_notify_uuid=_env_optional('PRINTER_BLE_NOTIFY_UUID'),
            ble_prefer_fast_write=_env_bool('PRINTER_BLE_PREFER_FAST_WRITE', False),
            ble_write_delay=_env_float('PRINTER_BLE_WRITE_DELAY', 0.0),

            ping_interval=_env_float('PING_INTERVAL', 60.0),
            event_interval=_env_float('EVENT_INTERVAL', 1.0),
            offline_interval=_env_float('OFFLINE_INTERVAL', 5.0),
            startup_interval=_env_float('STARTUP_INTERVAL', 1.0),
            guard_ping_interval=guard_ping_interval,

            font_size=_env_int('PRINT_TEXT_FONT_SIZE', 32),
            align=_env_str('PRINT_TEXT_ALIGN', 'left'),
            break_size=_env_int('PRINT_BREAK_SIZE', 100),
            battery_poll_interval=_env_float('BATTERY_POLL_INTERVAL', 300.0),

            discovery_retry_attempts=_env_int('DISCOVERY_RETRY_ATTEMPTS', 5),
            discovery_retry_backoff=_env_float('DISCOVERY_RETRY_BACKOFF', 5.0),
        )
