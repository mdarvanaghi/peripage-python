#!/usr/bin/env python3

"""
Print solid black bars of known dot-height, for calibrating a printer's
`aspect_correction` (see `PrinterTypeSpecs` in `peripage/protocol.py`).

Measure each printed bar's length in mm and compare against its expected
length (row_count * horizontal_mm_per_dot) to derive the correction
factor for a given printer type and transport configuration. Transport
settings (write batching, acknowledged vs. unacknowledged writes) affect
sustained print timing, so calibrate against the same transport
configuration you intend to use in production - see the Recommendations
section in the README.

Usage:
    python3 scripts/print_bar.py --printer P21 --address <address> \\
        --write-uuid <uuid> --notify-uuid <uuid> --rows 20 150 380

    python3 scripts/print_bar.py --printer A6 --mac <mac> --rows 100
"""

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage import Printer, PrinterType


def build_transport(args):
    if args.mac:
        from peripage.transport import SocketTransport
        return SocketTransport(args.mac, timeout=args.timeout)

    if args.address and args.write_uuid:
        from peripage.transport import BleakTransport
        return BleakTransport(
            address=args.address,
            write_characteristic=args.write_uuid,
            notify_characteristic=args.notify_uuid,
            timeout=args.timeout,
            prefer_fast_write=args.prefer_fast_write,
        )

    raise SystemExit('Provide either --mac (classic Bluetooth) or --address/--write-uuid (BLE)')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--printer', required=True, help=f'Printer type. One of: {", ".join(PrinterType.names())}')
    parser.add_argument('--mac', help='Bluetooth MAC address (classic transport)')
    parser.add_argument('--address', help='BLE device address (BLE transport)')
    parser.add_argument('--write-uuid', help='GATT write characteristic UUID (BLE transport)')
    parser.add_argument('--notify-uuid', help='GATT notify characteristic UUID (BLE transport, optional)')
    parser.add_argument('--prefer-fast-write', action='store_true', help='Use unacknowledged BLE writes (only if verified reliable on your device)')
    parser.add_argument('--timeout', type=float, default=10.0)
    parser.add_argument('--break-size', type=int, default=60, help='Paper feed between bars')
    parser.add_argument('--rows', type=int, nargs='+', default=[20, 150, 380], help='Dot-row heights to print, one bar each')
    args = parser.parse_args()

    if args.printer not in PrinterType.names():
        raise SystemExit(f'Unknown --printer {args.printer!r}. Choices: {", ".join(PrinterType.names())}')

    transport = build_transport(args)
    printer = Printer(transport, PrinterType[args.printer])
    printer.connect()
    printer.reset()

    row_bytes = printer.getRowBytes()
    solid_row = b'\xff' * row_bytes

    for i, rows in enumerate(args.rows):
        print(f'Printing bar {i + 1}/{len(args.rows)}: {rows} dot rows tall ...')
        printer.printImageBytes(solid_row * rows)
        time.sleep(0.5)
        printer.printBreak(args.break_size)
        time.sleep(0.5)

    printer.disconnect()

    print('\nMeasure the solid black length of each bar in mm (not the blank gaps).')
    for rows in args.rows:
        print(f'  {rows} rows -> ___ mm')


if __name__ == '__main__':
    main()
