#!/usr/bin/env python3

"""
Report the negotiated BLE ATT MTU for a connection. A small MTU (the BLE
default is 23, giving only 20 usable payload bytes per write) means
BleakTransport has to split data into many tiny chunks - each one, if
using acknowledged writes, costs a full round-trip. For a long/sustained
print, that round-trip overhead can make data delivery slower than the
printer's internal print engine consumes it, which shows up as visibly
stretched paper (the motor free-feeds while waiting for the next chunk).

Usage:
    python3 scripts/check_mtu.py <address> <write_uuid> <notify_uuid>
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage.transport.ble_transport import BleakTransport


def main():
    if len(sys.argv) != 4:
        print(f'Usage: python3 {sys.argv[0]} <address> <write_uuid> <notify_uuid>')
        sys.exit(1)

    address, write_uuid, notify_uuid = sys.argv[1], sys.argv[2], sys.argv[3]

    transport = BleakTransport(address=address, write_characteristic=write_uuid, notify_characteristic=notify_uuid, timeout=10.0)
    transport.connect()

    mtu = getattr(transport.client, 'mtu_size', None)
    print(f'Negotiated MTU: {mtu}')
    print(f'Usable write payload per chunk: {(mtu - 3) if mtu else "unknown"} bytes')
    if mtu and mtu <= 23:
        print('This is the BLE default/minimum MTU - no negotiation happened. '
              'Every write is being split into very small chunks, which is a strong '
              'candidate for causing sustained-print throughput issues.')

    transport.disconnect()


if __name__ == '__main__':
    main()
