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

import asyncio
import threading
import typing

from peripage.transport.base import Transport


class BleakTransport(Transport):
    """
    Bluetooth Low Energy transport, backed by `bleak`.

    Used by the P21 (and, presumably, any other BLE-only Peripage model).
    `bleak`'s client API is `asyncio`-native, but `Transport` is a plain
    synchronous interface (to match the rest of the protocol layer, and
    the original PyBluez-socket behaviour). To bridge the two, this class
    runs a dedicated background thread with its own event loop for the
    lifetime of the transport; every public method submits a coroutine to
    that loop and blocks for the result.

    You need the GATT **write characteristic UUID** (and, if the printer
    ever talks back, the **notify characteristic UUID**) for your device.
    If you don't have them yet, run the discovery helper first:

        python3 -m peripage.transport.ble_discover scan
        python3 -m peripage.transport.ble_discover services <address>

    Look for a characteristic with `write` or `write-without-response` in
    its properties (that's your write characteristic) and one with
    `notify` (that's your notify characteristic, if present).
    """

    def __init__(
        self,
        address: str,
        write_characteristic: str,
        notify_characteristic: typing.Optional[str] = None,
        timeout: float = 10.0,
        prefer_fast_write: bool = False,
        write_delay: float = 0.0,
    ):
        """
        Arguments:
        * `address` - BLE address (or, on some platforms, UUID) of the
          printer, as reported by `ble_discover.py scan`.
        * `write_characteristic` - UUID of the GATT characteristic to
          write printer opcodes to.
        * `notify_characteristic` - UUID of the GATT characteristic to
          subscribe to for responses. Optional - if the printer never
          answers anything you care about, omit it; `recv()` will then
          always time out and return `b''`, matching how a real socket
          behaves when nothing arrives.
        * `timeout` - connect / write / recv timeout in seconds.
        * `prefer_fast_write` - if the write characteristic supports both
          acknowledged ("write") and unacknowledged
          ("write-without-response") writes, prefer the unacknowledged
          mode for speed. Default is `False`: acknowledged writes are
          used whenever available, since each acknowledged write blocks
          until the peripheral confirms it, which acts as flow control.
          Unacknowledged writes have no such backpressure - if you send
          faster than the printer's BLE stack can drain its buffer,
          chunks get silently dropped and the print comes out corrupted.
          Only flip this on if you've confirmed prints stay correct with
          it on your specific device.
        * `write_delay` - extra `asyncio.sleep()` after every chunk write,
          in seconds. Independent of `prefer_fast_write` - this paces
          *how often* chunks go out, not whether each one is acknowledged.
          Useful for diagnosing/working around printers whose internal
          print engine runs continuously and free-feeds paper when its
          receive buffer runs low (data-starvation causes visible
          stretching, distinct from dropped-packet corruption). Default
          `0.0` (no extra delay).
        """

        self.address = address
        self.write_characteristic = write_characteristic
        self.notify_characteristic = notify_characteristic
        self.timeout = timeout
        self.prefer_fast_write = prefer_fast_write
        self.write_delay = write_delay

        self.client = None
        self._write_without_response = False
        self._send_buffer = bytearray()

        self._loop: typing.Optional[asyncio.AbstractEventLoop] = None
        self._thread: typing.Optional[threading.Thread] = None
        self._notify_queue: typing.Optional[asyncio.Queue] = None

    # -- event loop plumbing -------------------------------------------------

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return

        ready = threading.Event()

        def _run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        ready.wait()

    def _run(self, coro: typing.Coroutine, timeout: typing.Optional[float] = None):
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout if timeout is not None else self.timeout)

    # -- notifications --------------------------------------------------------

    def _on_notify(self, _sender, data: bytearray) -> None:
        # Runs inside the loop thread (bleak's callback contract), so it's
        # safe to touch the asyncio.Queue directly here.
        if self._notify_queue is not None:
            self._notify_queue.put_nowait(bytes(data))

    # -- Transport interface --------------------------------------------------

    def connect(self) -> None:
        self._run(self._async_connect())

    async def _async_connect(self) -> None:
        from bleak import BleakClient

        self.client = BleakClient(self.address, timeout=self.timeout)
        await self.client.connect()
        self._notify_queue = asyncio.Queue()
        self._send_buffer = bytearray()

        # Determine write mode. Acknowledged writes ("write") give free
        # flow control - each call blocks until the peripheral confirms
        # it received the chunk - so they're preferred by default.
        # Unacknowledged writes ("write-without-response") are only used
        # if that's all the characteristic supports, or if the caller
        # explicitly opted into speed over reliability.
        char = self.client.services.get_characteristic(self.write_characteristic)
        props = [p.lower() for p in char.properties] if char is not None else []
        supports_response = 'write' in props
        supports_no_response = 'write-without-response' in props

        if self.prefer_fast_write and supports_no_response:
            self._write_without_response = True
        elif supports_response:
            self._write_without_response = False
        elif supports_no_response:
            self._write_without_response = True
        else:
            self._write_without_response = False

        if self.notify_characteristic:
            await self.client.start_notify(self.notify_characteristic, self._on_notify)

    def disconnect(self) -> None:
        if self.client is None:
            return
        try:
            self._run(self._async_flush())
        except Exception:
            pass
        try:
            self._run(self._async_disconnect())
        finally:
            self.client = None

    async def _async_disconnect(self) -> None:
        if self.notify_characteristic:
            try:
                await self.client.stop_notify(self.notify_characteristic)
            except Exception:
                pass
        await self.client.disconnect()

    def is_connected(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self._run(self._async_is_connected()))
        except Exception:
            return False

    async def _async_is_connected(self) -> bool:
        return self.client.is_connected

    def set_timeout(self, timeout: float) -> None:
        self.timeout = timeout

    def send(self, data: bytes) -> None:
        self._run(self._async_send(bytes(data)))

    async def _async_send(self, data: bytes) -> None:
        # GATT writes are capped by the negotiated ATT MTU (payload is
        # mtu - 3 bytes of header). The printer protocol has no concept of
        # this (it was written for a byte-stream socket) - it calls
        # send() once per small chunk (e.g. a ~53-byte row: preamble +
        # row bytes). Naively writing each one as its own BLE transaction
        # wastes most of the MTU's capacity and pays a full round-trip
        # per row. Since the printer just wants a continuous byte stream
        # in order, we instead buffer here and only actually write once
        # we've accumulated a full MTU's worth (or flush() is called
        # explicitly - see recv()/disconnect()) - so e.g. ~4 rows go out
        # per BLE transaction instead of 4 separate ones.
        mtu = getattr(self.client, 'mtu_size', None) or 20
        chunk_size = max(1, mtu - 3)

        self._send_buffer.extend(data)
        while len(self._send_buffer) >= chunk_size:
            chunk = bytes(self._send_buffer[:chunk_size])
            del self._send_buffer[:chunk_size]
            await self._write_chunk(chunk)

    async def _write_chunk(self, chunk: bytes) -> None:
        await self.client.write_gatt_char(
            self.write_characteristic,
            chunk,
            response=not self._write_without_response,
        )
        if self.write_delay > 0:
            await asyncio.sleep(self.write_delay)

    def flush(self) -> None:
        """
        Force out any bytes buffered by send()'s batching, even if they
        don't fill a full MTU chunk. Called automatically before recv()
        (so a pending write is guaranteed to have actually reached the
        printer before we wait for its response) and before disconnect()
        (so nothing buffered gets silently dropped on close). Safe to
        call manually too, e.g. after a batch of printBreak()/printRow()
        calls if you want to guarantee they've actually been transmitted.
        """

        self._run(self._async_flush())

    async def _async_flush(self) -> None:
        if self._send_buffer:
            chunk = bytes(self._send_buffer)
            self._send_buffer.clear()
            await self._write_chunk(chunk)

    def recv(self, size: int = 1024) -> bytes:
        self.flush()
        return self._run(self._async_recv(size), timeout=self.timeout + 0.5)

    async def _async_recv(self, size: int) -> bytes:
        if self._notify_queue is None:
            return b''
        try:
            data = await asyncio.wait_for(self._notify_queue.get(), timeout=self.timeout)
        except asyncio.TimeoutError:
            return b''
        return data[:size]
