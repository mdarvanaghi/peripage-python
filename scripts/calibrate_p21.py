#!/usr/bin/env python3

"""
P21 vertical-feed calibration.

Prints three solid black bars of known dot-height (20, 150, 380 dot rows -
the last one deliberately crosses the printer's 255-row chunk boundary, in
case that's contributing extra fixed-length overhead per chunk/reset). Each
bar is full-width so it's unambiguous where it starts/ends on the paper.
Measure each bar's length in mm and report back.

Usage:
    python3 scripts/calibrate_p21.py <address> <write_uuid> <notify_uuid>
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage import Printer, PrinterType
from peripage.transport.ble_transport import BleakTransport

BAR_HEIGHTS = [20, 150, 380]


def main():
    if len(sys.argv) != 4:
        print(f'Usage: python3 {sys.argv[0]} <address> <write_uuid> <notify_uuid>')
        sys.exit(1)

    address, write_uuid, notify_uuid = sys.argv[1], sys.argv[2], sys.argv[3]

    transport = BleakTransport(
        address=address,
        write_characteristic=write_uuid,
        notify_characteristic=notify_uuid,
        timeout=10.0,
        prefer_fast_write=True,
    )
    printer = Printer(transport, PrinterType.P21)
    printer.connect()
    printer.reset()

    row_bytes = printer.getRowBytes()
    solid_row = b'\xff' * row_bytes

    for i, height in enumerate(BAR_HEIGHTS):
        print(f'\nPrinting bar {i + 1}/{len(BAR_HEIGHTS)}: {height} dot rows tall ...')
        printer.printImageBytes(solid_row * height)
        time.sleep(0.5)
        # Feed enough blank paper between bars that they're unambiguous, and
        # mark it verbally since we can't print text.
        printer.printBreak(60)
        time.sleep(0.5)
        print(f'  Done. This bar should be clearly separated from the next by blank paper.')

    printer.disconnect()

    print('\nAll bars printed. For each one, measure the SOLID BLACK length in mm')
    print('(not the blank gaps) and report back three numbers, in order:')
    print(f'  {BAR_HEIGHTS[0]} rows -> ___ mm')
    print(f'  {BAR_HEIGHTS[1]} rows -> ___ mm')
    print(f'  {BAR_HEIGHTS[2]} rows -> ___ mm')


if __name__ == '__main__':
    main()
