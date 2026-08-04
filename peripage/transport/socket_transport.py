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

from peripage.transport.base import Transport


class SocketTransport(Transport):
    """
    Classic Bluetooth (RFCOMM/SPP) transport, backed by `PyBluez`.

    This is a straight extraction of the socket handling that used to live
    directly on `peripage.Printer` (`connect`, `reconnect`, `disconnect`,
    `isConnected`, `setTimeout`, and the `sock.send`/`sock.recv` calls
    inside `tellPrinter`/`askPrinter`/etc). Behaviour is unchanged: same
    RFCOMM channel (`1`), same default timeout, same exception-swallowing
    `is_connected()` check.

    Used by the A6 / A6+ / A40 / A40+ printer models.

    `PyBluez` is imported lazily so that BLE-only usage (e.g. the P21 via
    `BleakTransport`) does not require `PyBluez` to be installed - it has
    native-extension dependencies (bluez headers) that are unnecessary
    dead weight if you never touch classic Bluetooth.
    """

    def __init__(self, mac: str, timeout: float = 1.0, channel: int = 1):
        """
        Arguments:
        * `mac` - MAC address of the printer.
        * `timeout` - socket connection timeout in seconds.
        * `channel` - RFCOMM channel to connect to. All known Peripage
          printers use channel `1`.
        """

        self.mac = mac
        self.timeout = timeout
        self.channel = channel
        self.sock = None

    def connect(self) -> None:
        import bluetooth

        self.sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        self.sock.connect((self.mac, self.channel))
        self.sock.settimeout(self.timeout)

    def disconnect(self) -> None:
        if self.is_connected():
            self.sock.close()
        self.sock = None

    def is_connected(self) -> bool:
        if self.sock is None:
            return False
        try:
            self.sock.getpeername()
            return True
        except Exception:
            return False

    def set_timeout(self, timeout: float) -> None:
        self.timeout = timeout
        if self.is_connected():
            self.sock.settimeout(timeout)

    def send(self, data: bytes) -> None:
        self.sock.send(data)

    def recv(self, size: int = 1024) -> bytes:
        return self.sock.recv(size)
