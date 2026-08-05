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
Resolves the `Config` into a connected-but-not-yet-`connect()`ed
`peripage.transport.Transport` instance.

Classic Bluetooth (A6/A6+/A40/A40+) always requires a configured MAC -
PyBluez's `discover_devices()` is exactly as ambiguous as the BLE name-filter
scan below (same "which discovered device is my printer" problem) but without
BLE's GATT table to auto-derive anything useful from, so there's no payoff to
scanning for it. BLE (P21) can auto-discover: scan for nearby devices, filter
by advertised name, then walk the GATT table to auto-pick a write/notify
characteristic.
"""

import asyncio
import logging
import typing

from config import Config

logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """Raised when the configured/auto-discovered printer can't be resolved
    to a transport. Caller should retry with backoff - this is expected to
    happen transiently (printer asleep/out of range) as well as fatally
    (bad config)."""


def resolve_ble_transport(cfg: Config):
    from peripage.transport import BleakTransport
    from peripage.transport import ble_discover

    address = cfg.ble_address
    write_uuid = cfg.ble_write_uuid
    notify_uuid = cfg.ble_notify_uuid

    if not address or not write_uuid:
        address, discovered_write, discovered_notify = asyncio.run(
            _scan_and_pick(cfg.ble_name_filter, cfg.ble_scan_timeout, cfg.printer_timeout)
        )
        write_uuid = write_uuid or discovered_write
        notify_uuid = notify_uuid or discovered_notify

    if not write_uuid:
        raise DiscoveryError(
            f'No write characteristic found for {address!r}. '
            'Set PRINTER_BLE_WRITE_UUID explicitly, or check with:\n'
            f'  python -m peripage.transport.ble_discover services {address}'
        )

    return BleakTransport(
        address,
        write_characteristic=write_uuid,
        notify_characteristic=notify_uuid,
        timeout=cfg.printer_timeout,
        prefer_fast_write=cfg.ble_prefer_fast_write,
        write_delay=cfg.ble_write_delay,
    )


async def _scan_and_pick(name_filter: str, scan_timeout: float, gatt_timeout: float):
    from peripage.transport import ble_discover

    devices = await ble_discover.scan_devices(timeout=scan_timeout)
    needle = name_filter.lower()
    matches = [d for d in devices if d.name and needle in d.name.lower()]

    if not matches:
        raise DiscoveryError(
            f'No BLE device found matching name filter {name_filter!r} '
            f'(scanned {len(devices)} device(s)). Is the printer powered on and in range?'
        )

    if len(matches) > 1:
        candidates = ', '.join(f'{d.address} ({d.name})' for d in matches)
        logger.warning(
            'Multiple BLE devices matched name filter %r: %s - picking the first one. '
            'Set PRINTER_BLE_ADDRESS to pin a specific device.',
            name_filter, candidates,
        )

    address = matches[0].address
    table = await ble_discover.list_gatt_table(address, timeout=gatt_timeout)

    write_uuid = None
    notify_uuid = None
    for service in table:
        for char in service['characteristics']:
            props = [p.lower() for p in char['properties']]
            if write_uuid is None and ('write' in props or 'write-without-response' in props):
                write_uuid = char['uuid']
            if notify_uuid is None and ('notify' in props or 'indicate' in props):
                notify_uuid = char['uuid']

    return address, write_uuid, notify_uuid


def resolve_classic_transport(cfg: Config):
    from peripage.transport import SocketTransport

    if not cfg.mac:
        raise DiscoveryError('PRINTER_MAC is required for PRINTER_TRANSPORT=classic')

    return SocketTransport(cfg.mac, timeout=cfg.printer_timeout)


def build_transport(cfg: Config):
    """
    Mirrors `peripage/cli.py`'s `_build_transport()` branching.
    """

    if cfg.transport_kind == 'classic':
        return resolve_classic_transport(cfg)
    if cfg.transport_kind == 'ble':
        return resolve_ble_transport(cfg)
    raise DiscoveryError(f'Unknown PRINTER_TRANSPORT {cfg.transport_kind!r}')
