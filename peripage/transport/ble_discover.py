#!/usr/bin/env python3

# peripage-python - python library for peripage thermal printers
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
Standalone helper to find a BLE printer's address and GATT characteristic
UUIDs, so you can configure `BleakTransport` without any other tooling.

Usage:
    python3 -m peripage.transport.ble_discover scan [--timeout SECONDS]
    python3 -m peripage.transport.ble_discover services ADDRESS [--timeout SECONDS]

Workflow:
1. Run `scan` with the printer powered on and in range. Note the address
   of the device that looks like your printer (e.g. name containing
   "PeriPage" or "P21").
2. Run `services ADDRESS` with that address. Look through the printed
   GATT table for a characteristic whose properties include `write` or
   `write-without-response` - that's your write characteristic. If one
   also has `notify`, that's your notify characteristic (may be the same
   service, a different characteristic).
3. Pass those UUIDs to `BleakTransport(address, write_characteristic=...,
   notify_characteristic=...)`.
"""

import argparse
import asyncio
import sys


async def scan_devices(timeout: float = 5.0):
    from bleak import BleakScanner

    return await BleakScanner.discover(timeout=timeout)


async def list_gatt_table(address: str, timeout: float = 10.0):
    from bleak import BleakClient

    table = []
    async with BleakClient(address, timeout=timeout) as client:
        for service in client.services:
            characteristics = []
            for char in service.characteristics:
                characteristics.append({
                    'uuid': char.uuid,
                    'handle': char.handle,
                    'properties': list(char.properties),
                })
            table.append({
                'uuid': service.uuid,
                'characteristics': characteristics,
            })
    return table


def run_scan(timeout: float = 5.0):
    print(f'Scanning for {timeout:.0f}s ... (make sure the printer is on and awake)\n')
    devices = asyncio.run(scan_devices(timeout))

    if not devices:
        print('No BLE devices found. Try moving closer, waking the printer '
              '(press its power button), or increasing --timeout.')
        return

    for d in devices:
        name = d.name or '(unnamed)'
        print(f'{d.address}   {name}')


def run_services(address: str, timeout: float = 10.0):
    print(f'Connecting to {address} ...\n')
    table = asyncio.run(list_gatt_table(address, timeout))

    if not table:
        print('No services reported.')
        return

    for service in table:
        print(f'Service {service["uuid"]}')
        for c in service['characteristics']:
            flag = ''
            props = [p.lower() for p in c['properties']]
            if 'write' in props or 'write-without-response' in props:
                flag += '  <-- candidate WRITE characteristic'
            if 'notify' in props or 'indicate' in props:
                flag += '  <-- candidate NOTIFY characteristic'
            print(f'  Characteristic {c["uuid"]}  handle={c["handle"]}  properties={c["properties"]}{flag}')
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    scan_parser = sub.add_parser('scan', help='Scan for nearby BLE devices')
    scan_parser.add_argument('--timeout', type=float, default=5.0, help='Scan duration in seconds')

    services_parser = sub.add_parser('services', help='List GATT services/characteristics for a device')
    services_parser.add_argument('address', type=str, help='BLE address from `scan`')
    services_parser.add_argument('--timeout', type=float, default=10.0, help='Connect timeout in seconds')

    args = parser.parse_args()

    if args.command == 'scan':
        run_scan(args.timeout)
    elif args.command == 'services':
        run_services(args.address, args.timeout)


if __name__ == '__main__':
    main()
