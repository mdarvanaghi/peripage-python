# peripage-python - python library for peripage thermal printers
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# Milestone 2 verification, part 1: exercises BleakTransport's own logic
# (MTU-aware write chunking, the async-loop-in-a-thread bridge, notify
# queueing) against a fake stand-in for bleak.BleakClient. This is *not* a
# substitute for testing against the real P21 - it cannot verify that the
# UUIDs/opcodes are actually correct for that hardware - but it does prove
# the transport's plumbing is sound before you spend time on real hardware.

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import bleak
from peripage.transport.ble_transport import BleakTransport


class FakeCharacteristic:
    def __init__(self, uuid, properties):
        self.uuid = uuid
        self.properties = properties
        self.handle = 1


class FakeServices:
    def __init__(self, characteristics):
        self._characteristics = characteristics

    def get_characteristic(self, uuid):
        return self._characteristics.get(uuid)


class FakeBleakClient:
    """Stand-in for bleak.BleakClient, good enough to exercise BleakTransport."""

    WRITE_UUID = '0000ff01-0000-1000-8000-00805f9b34fb'
    NOTIFY_UUID = '0000ff02-0000-1000-8000-00805f9b34fb'

    def __init__(self, address, timeout=10.0):
        self.address = address
        self.timeout = timeout
        self._connected = False
        self.mtu_size = 23  # deliberately small/default-ish, to exercise chunking
        self.writes = []  # list of (uuid, bytes, response_bool)
        self._notify_callback = None
        self.services = FakeServices({
            self.WRITE_UUID: FakeCharacteristic(self.WRITE_UUID, ['write', 'write-without-response']),
            self.NOTIFY_UUID: FakeCharacteristic(self.NOTIFY_UUID, ['notify']),
        })

    async def connect(self):
        self._connected = True

    async def disconnect(self):
        self._connected = False

    @property
    def is_connected(self):
        return self._connected

    async def write_gatt_char(self, uuid, data, response=True):
        assert len(data) <= self.mtu_size - 3, 'write exceeded MTU payload limit'
        self.writes.append((uuid, bytes(data), response))

    async def start_notify(self, uuid, callback):
        self._notify_callback = callback

    async def stop_notify(self, uuid):
        self._notify_callback = None

    def simulate_notification(self, data: bytes):
        """Test helper: pretend the printer just sent `data` back."""
        assert self._notify_callback is not None, 'start_notify was never called'
        self._notify_callback(self.NOTIFY_UUID, bytearray(data))


def make_transport(monkeypatch_client):
    bleak.BleakClient = monkeypatch_client
    transport = BleakTransport(
        address='AA:BB:CC:DD:EE:FF',
        write_characteristic=FakeBleakClient.WRITE_UUID,
        notify_characteristic=FakeBleakClient.NOTIFY_UUID,
        timeout=2.0,
    )
    return transport


def test_connect_and_is_connected():
    transport = make_transport(FakeBleakClient)
    transport.connect()
    assert transport.is_connected() is True
    transport.disconnect()
    assert transport.is_connected() is False


def test_send_chunks_to_mtu():
    transport = make_transport(FakeBleakClient)
    transport.connect()

    payload = bytes(range(50))  # 50 bytes, MTU payload cap is 23-3=20
    transport.send(payload)
    transport.flush()  # flush the trailing partial (10-byte) chunk

    fake_client = transport.client
    reassembled = b''.join(w[1] for w in fake_client.writes)
    assert reassembled == payload
    assert all(len(w[1]) <= 20 for w in fake_client.writes)
    assert len(fake_client.writes) == 3  # 20 + 20 + 10

    transport.disconnect()


def test_acknowledged_write_by_default():
    # ff02-style characteristics that support both modes should default to
    # acknowledged writes (response=True), since that's what gives flow
    # control and avoids silently-dropped chunks.
    transport = make_transport(FakeBleakClient)
    transport.connect()
    transport.send(b'\x01\x02\x03')
    transport.flush()  # 3 bytes alone never fills a 20-byte chunk
    fake_client = transport.client
    assert fake_client.writes[-1][2] is True
    transport.disconnect()


def test_prefer_fast_write_opts_into_unacknowledged():
    bleak.BleakClient = FakeBleakClient
    transport = BleakTransport(
        address='AA:BB:CC:DD:EE:FF',
        write_characteristic=FakeBleakClient.WRITE_UUID,
        notify_characteristic=FakeBleakClient.NOTIFY_UUID,
        timeout=2.0,
        prefer_fast_write=True,
    )
    transport.connect()
    transport.send(b'\x01\x02\x03')
    transport.flush()
    fake_client = transport.client
    assert fake_client.writes[-1][2] is False
    transport.disconnect()


def test_recv_returns_notified_bytes():
    transport = make_transport(FakeBleakClient)
    transport.connect()

    fake_client = transport.client
    fake_client.simulate_notification(b'PONG')

    result = transport.recv()
    assert result == b'PONG'
    transport.disconnect()


def test_recv_times_out_to_empty_bytes():
    transport = make_transport(FakeBleakClient)
    transport.set_timeout(0.3)
    transport.connect()

    result = transport.recv()
    assert result == b''
    transport.disconnect()


def test_write_delay_paces_chunks():
    import time

    bleak.BleakClient = FakeBleakClient
    transport = BleakTransport(
        address='AA:BB:CC:DD:EE:FF',
        write_characteristic=FakeBleakClient.WRITE_UUID,
        notify_characteristic=FakeBleakClient.NOTIFY_UUID,
        timeout=2.0,
        write_delay=0.05,
    )
    transport.connect()

    payload = bytes(range(50))  # forces 3 chunks against the 23-byte MTU fake client
    start = time.monotonic()
    transport.send(payload)
    transport.flush()
    elapsed = time.monotonic() - start

    # 3 chunks * 0.05s delay each, roughly (allow generous slack for CI jitter)
    assert elapsed >= 0.12, f'expected write_delay to add measurable pacing, took {elapsed:.3f}s'
    transport.disconnect()


def test_small_sends_are_batched_into_fewer_writes():
    # This is the actual optimization: the printer protocol calls send()
    # once per small chunk (e.g. ~5-byte header + 48-byte row = 53 bytes
    # per row). Against a generous MTU (237 usable bytes, like the P21's),
    # ~4 of those should collapse into a single physical BLE write instead
    # of 4 separate round-trips.
    bleak.BleakClient = FakeBleakClient
    transport = BleakTransport(
        address='AA:BB:CC:DD:EE:FF',
        write_characteristic=FakeBleakClient.WRITE_UUID,
        notify_characteristic=FakeBleakClient.NOTIFY_UUID,
        timeout=2.0,
    )
    transport.connect()
    transport.client.mtu_size = 240  # override the fake's default small MTU

    row = bytes(range(53))
    for _ in range(8):
        transport.send(row)
    transport.flush()

    fake_client = transport.client
    reassembled = b''.join(w[1] for w in fake_client.writes)
    assert reassembled == row * 8
    # 8 rows * 53 bytes = 424 bytes, chunked at 237 -> 1 full (237) + 1 partial
    # (187) = 2 writes, instead of 8 separate one-per-row writes.
    assert len(fake_client.writes) == 2, f'expected batching to reduce write count, got {len(fake_client.writes)} writes'

    transport.disconnect()


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
