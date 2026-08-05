# peripage-python - Home Assistant MQTT daemon tests
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# Verifies ha-mqtt-daemon/discovery.py's BLE scan-and-pick logic without any
# real BLE stack: monkeypatches peripage.transport.ble_discover's
# scan_devices/list_gatt_table with canned data.

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ha-mqtt-daemon'))

from peripage.transport import ble_discover
import discovery


class FakeDevice:
    def __init__(self, address, name):
        self.address = address
        self.name = name


def _patch_scan(devices):
    async def fake_scan_devices(timeout=5.0):
        return devices
    ble_discover.scan_devices = fake_scan_devices


def _patch_gatt(table):
    async def fake_list_gatt_table(address, timeout=10.0):
        return table
    ble_discover.list_gatt_table = fake_list_gatt_table


GATT_TABLE = [{
    'uuid': 'service-1',
    'characteristics': [
        {'uuid': 'write-uuid', 'handle': 1, 'properties': ['write', 'write-without-response']},
        {'uuid': 'notify-uuid', 'handle': 2, 'properties': ['notify']},
        {'uuid': 'other-uuid', 'handle': 3, 'properties': ['read']},
    ],
}]


def test_scan_and_pick_matches_by_name_filter():
    _patch_scan([FakeDevice('AA:BB:CC:DD:EE:01', 'Some Other Device'),
                 FakeDevice('AA:BB:CC:DD:EE:02', 'PeriPage+ABCD')])
    _patch_gatt(GATT_TABLE)

    address, write_uuid, notify_uuid = asyncio.run(discovery._scan_and_pick('PeriPage', 5.0, 10.0))

    assert address == 'AA:BB:CC:DD:EE:02'
    assert write_uuid == 'write-uuid'
    assert notify_uuid == 'notify-uuid'


def test_scan_and_pick_raises_when_no_match():
    _patch_scan([FakeDevice('AA:BB:CC:DD:EE:01', 'Some Other Device')])
    _patch_gatt(GATT_TABLE)

    try:
        asyncio.run(discovery._scan_and_pick('PeriPage', 5.0, 10.0))
        assert False, 'expected DiscoveryError'
    except discovery.DiscoveryError:
        pass


def test_scan_and_pick_ignores_unnamed_devices():
    _patch_scan([FakeDevice('AA:BB:CC:DD:EE:01', None)])
    _patch_gatt(GATT_TABLE)

    try:
        asyncio.run(discovery._scan_and_pick('PeriPage', 5.0, 10.0))
        assert False, 'expected DiscoveryError'
    except discovery.DiscoveryError:
        pass


def test_scan_and_pick_first_match_on_ambiguity():
    _patch_scan([FakeDevice('AA:BB:CC:DD:EE:01', 'PeriPage+AAAA'),
                 FakeDevice('AA:BB:CC:DD:EE:02', 'PeriPage+BBBB')])
    _patch_gatt(GATT_TABLE)

    address, write_uuid, notify_uuid = asyncio.run(discovery._scan_and_pick('PeriPage', 5.0, 10.0))

    assert address == 'AA:BB:CC:DD:EE:01'


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    sys.exit(1 if failed else 0)
