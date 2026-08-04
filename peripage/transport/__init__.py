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
from peripage.transport.socket_transport import SocketTransport
from peripage.transport.fake_transport import FakeTransport

__all__ = ['Transport', 'SocketTransport', 'FakeTransport', 'BleakTransport']


def __getattr__(name):
    # `bleak` is an optional dependency (only needed for BLE printers like
    # the P21), so it's imported lazily here rather than at module load
    # time. `from peripage.transport import BleakTransport` still works;
    # it just defers the `bleak` import until the name is actually used.
    if name == 'BleakTransport':
        from peripage.transport.ble_transport import BleakTransport
        return BleakTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
