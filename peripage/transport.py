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


import abc
import typing
import asyncio
import sys

# Try to import bleak for BLE support
try:
    from bleak import BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    BleakClient = None


class Transport(abc.ABC):
    """Abstract base class for transport layers."""

    @abc.abstractmethod
    def connect(self) -> None:
        """Establish a connection to the device."""
        pass

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Close the connection to the device."""
        pass

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Check if the connection is active."""
        pass

    @abc.abstractmethod
    def set_timeout(self, timeout: float) -> None:
        """Set the operation timeout."""
        pass

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Send data to the device."""
        pass

    @abc.abstractmethod
    def read(self, size: int) -> bytes:
        """Receive data from the device."""
        pass


class BleakTransport(Transport):
    """Bluetooth Low Energy transport using Bleak (NUS service)."""

    def __init__(self, mac: str, timeout: float = 1.0):
        if not BLEAK_AVAILABLE:
            raise ImportError("The 'bleak' module is required for BleakTransport")
        self.mac = mac
        self.timeout = timeout
        self.client: typing.Optional[BleakClient] = None
        self.loop: typing.Optional[asyncio.AbstractEventLoop] = None
        self.tx_char = None  # UART TX characteristic (write without response)
        self.rx_char = None  # UART RX characteristic (notify/read)

    def _run_async(self, coro):
        """Run a coroutine in the event loop."""
        if self.loop is None or not self.loop.is_running():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop.run_until_complete(coro)

    def connect(self) -> None:
        """Establish a BLE connection and discover UART service."""
        async def _connect():
            self.client = BleakClient(self.mac)
            await self.client.connect(timeout=self.timeout)

            # Find UART Service (Nordic UART Service)
            uart_service = None
            for service in self.client.services:
                if service.uuid.lower() == "6e400001-b5a3-f393-e0a9-e50e24dcca9e".lower():
                    uart_service = service
                    break
            if uart_service is None:
                raise RuntimeError("UART Service not found on device")

            # Find TX and RX characteristics
            for char in uart_service.characteristics:
                if char.uuid.lower() == "6e400002-b5a3-f393-e0a9-e50e24dcca9e".lower():
                    self.tx_char = char
                elif char.uuid.lower() == "6e400003-b5a3-f393-e0a9-e50e24dcca9e".lower():
                    self.rx_char = char

            if self.tx_char is None or self.rx_char is None:
                raise RuntimeError("UART TX/RX characteristics not found")

        self._run_async(_connect())

    def disconnect(self) -> None:
        """Close the BLE connection."""
        async def _disconnect():
            if self.client and self.client.is_connected:
                await self.client.disconnect()

        self._run_async(_disconnect())
        self.client = None
        self.loop = None

    def is_connected(self) -> bool:
        """Check if the BLE connection is active."""
        return self.client is not None and self.client.is_connected

    def set_timeout(self, timeout: float) -> None:
        """Set the BLE operation timeout."""
        self.timeout = timeout

    def write(self, data: bytes) -> None:
        """Send data to the TX characteristic (without response)."""
        if not self.is_connected():
            raise ConnectionError("Not connected to device")
        async def _write():
            await self.client.write_gatt_char(self.tx_char, data, response=False)
        self._run_async(_write())

    def read(self, size: int) -> bytes:
        """Read data from the RX characteristic."""
        if not self.is_connected():
            raise ConnectionError("Not connected to device")
        async def _read():
            # Attempt to read the characteristic multiple times to get sufficient data
            data = bytearray()
            for _ in range(5):  # Try up to 5 times
                chunk = await self.client.read_gatt_char(self.rx_char, timeout=self.timeout)
                data.extend(chunk)
                if len(data) >= size:
                    break
                await asyncio.sleep(0.1)  # Wait between attempts
            # Return exactly 'size' bytes (truncate if needed)
            return bytes(data[:size])
        return self._run_async(_read())