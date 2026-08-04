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


class Transport(abc.ABC):
    """
    Abstract communication channel between `Printer` and a physical printer.

    The original implementation talked to the printer exclusively through a
    `PyBluez` classic-Bluetooth RFCOMM socket. Every place that touched
    `self.sock` now goes through an instance of this interface instead, so
    the protocol layer (`peripage.protocol.Printer`) has no knowledge of
    *how* bytes get to the printer - only that they do.

    Implementations:
    * `peripage.transport.socket_transport.SocketTransport` - classic
      Bluetooth RFCOMM via `PyBluez` (used by A6/A6+/A40/A40+).
    * `peripage.transport.ble_transport.BleakTransport` - Bluetooth Low
      Energy GATT via `bleak` (used by P21).
    * `peripage.transport.fake_transport.FakeTransport` - in-memory stub
      used for unit tests, no hardware required.
    """

    @abc.abstractmethod
    def connect(self) -> None:
        """
        Open a new connection to the printer without checking for an
        existing connection. Calling this while already connected may
        leave the previous connection in an unusable state - callers that
        want the "close old, open new" behaviour should use `reconnect()`.
        """

        raise NotImplementedError

    def reconnect(self) -> None:
        """
        Reconnect to the printer, closing any existing connection first.
        Default implementation just calls `disconnect()` then `connect()`;
        override if a backend needs different behaviour.
        """

        if self.is_connected():
            self.disconnect()
        self.connect()

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the printer. Must be safe to call when not connected."""

        raise NotImplementedError

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Check whether the underlying connection is currently alive."""

        raise NotImplementedError

    @abc.abstractmethod
    def set_timeout(self, timeout: float) -> None:
        """Set the send/receive timeout, in seconds."""

        raise NotImplementedError

    @abc.abstractmethod
    def send(self, data: bytes) -> None:
        """Send `data` to the printer without waiting for a response."""

        raise NotImplementedError

    @abc.abstractmethod
    def recv(self, size: int = 1024) -> bytes:
        """Receive up to `size` bytes from the printer, blocking until data
        arrives or `timeout` elapses."""

        raise NotImplementedError
