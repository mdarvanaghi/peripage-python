#!/usr/bin/env python3

"""
Milestone 2 hardware verification: connect to the P21 over BLE and feed a
bit of paper. Doesn't print an image yet (that needs the row geometry
calibrated in milestone 3) - this just proves BleakTransport + the
discovered UUIDs actually talk to the printer.

Usage:
    python3 scripts/test_p21_ble.py <address>
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage import Printer, PrinterType
from peripage.transport.ble_transport import BleakTransport

WRITE_CHARACTERISTIC = '0000ff02-0000-1000-8000-00805f9b34fb'
NOTIFY_CHARACTERISTIC = '0000ff01-0000-1000-8000-00805f9b34fb'


def main():
    if len(sys.argv) != 2:
        print(f'Usage: python3 {sys.argv[0]} <address>')
        sys.exit(1)

    address = sys.argv[1]

    print(f'Connecting to {address} ...')
    transport = BleakTransport(
        address=address,
        write_characteristic=WRITE_CHARACTERISTIC,
        notify_characteristic=NOTIFY_CHARACTERISTIC,
        timeout=10.0,
    )
    printer = Printer(transport, PrinterType.P21)
    printer.connect()
    print(f'Connected: {printer.isConnected()}')

    print('Sending reset() ...')
    printer.reset()
    time.sleep(0.5)

    print('Trying getDeviceName() (printer may or may not respond - not critical if it times out) ...')
    try:
        name = printer.getDeviceName()
        print(f'  Device name: {name!r}')
    except Exception as e:
        print(f'  No response / error: {e}')

    print('Feeding paper with printBreak() - watch the printer, paper should advance ...')
    printer.printBreak(0x40)
    time.sleep(1.0)

    printer.disconnect()
    print('Done. If the paper fed, BleakTransport + these UUIDs are confirmed working.')


if __name__ == '__main__':
    main()
