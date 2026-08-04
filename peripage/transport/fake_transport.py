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

import collections
import typing


class FakeTransport:
    """
    In-memory stand-in for a real transport, used for unit tests and for
    experimenting with `Printer` without any Bluetooth hardware.

    Every call to `send()` is recorded in `self.sent` (a list of `bytes`),
    so tests can assert on exactly what the protocol layer would have put
    on the wire. `recv()` pops queued canned responses set up ahead of time
    via `queue_response()`.
    """

    def __init__(self):
        self.connected = False
        self.timeout = 1.0
        self.sent: typing.List[bytes] = []
        self._responses: typing.Deque[bytes] = collections.deque()

    def queue_response(self, data: bytes) -> None:
        """Queue up bytes to be returned by the next `recv()` call."""

        self._responses.append(data)

    def connect(self) -> None:
        self.connected = True

    def reconnect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def set_timeout(self, timeout: float) -> None:
        self.timeout = timeout

    def send(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    def recv(self, size: int = 1024) -> bytes:
        if not self._responses:
            return b''
        return self._responses.popleft()[:size]

    def last_sent(self) -> bytes:
        """Convenience helper: the most recent bytes passed to `send()`."""

        return self.sent[-1] if self.sent else b''

    def all_sent(self) -> bytes:
        """Convenience helper: every byte ever sent, concatenated in order."""

        return b''.join(self.sent)
