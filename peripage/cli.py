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

import sys
import typing

import typer

import peripage
from peripage import Printer, PrinterType

app = typer.Typer(
    help='Print on a Peripage printer over classic Bluetooth (A6/A6+/A40/A40+) or BLE (P21).',
    no_args_is_help=True,
)

discover_app = typer.Typer(help='Find a BLE printer\'s address and GATT characteristic UUIDs (P21 and similar).')
app.add_typer(discover_app, name='discover')


class ConnectionState:
    def __init__(self, printer: Printer, concentration: int, break_size: int):
        self.printer = printer
        self.concentration = concentration
        self.break_size = break_size


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


def _build_transport(
    transport_kind: str,
    mac: typing.Optional[str],
    address: typing.Optional[str],
    write_uuid: typing.Optional[str],
    notify_uuid: typing.Optional[str],
    timeout: float,
    prefer_fast_write: bool = False,
    write_delay: float = 0.0,
):
    if transport_kind == 'classic':
        if not mac:
            raise _fail('--mac is required for --transport classic')
        from peripage.transport import SocketTransport
        return SocketTransport(mac, timeout=timeout)

    if transport_kind == 'ble':
        if not address or not write_uuid:
            raise _fail(
                '--address and --write-uuid are required for --transport ble.\n'
                'Don\'t know them yet? Run:\n'
                '  peripage discover scan\n'
                '  peripage discover services <address>'
            )
        from peripage.transport import BleakTransport
        return BleakTransport(
            address,
            write_characteristic=write_uuid,
            notify_characteristic=notify_uuid,
            timeout=timeout,
            prefer_fast_write=prefer_fast_write,
            write_delay=write_delay,
        )

    raise _fail(f'Unknown --transport {transport_kind!r}, expected "classic" or "ble"')


@app.callback()
def connection_options(
    ctx: typer.Context,
    printer: typing.Optional[str] = typer.Option(
        None, '--printer', '-p',
        help=f'Printer model. One of: {", ".join(PrinterType.names())}',
    ),
    transport: str = typer.Option(
        'ble', '--transport',
        help='"classic" (RFCOMM - A6/A6+/A40/A40+) or "ble" (P21)',
    ),
    mac: typing.Optional[str] = typer.Option(
        None, '--mac', '-m', help='Bluetooth MAC address (--transport classic)',
    ),
    address: typing.Optional[str] = typer.Option(
        None, '--address', '-a', help='BLE device address (--transport ble)',
    ),
    write_uuid: typing.Optional[str] = typer.Option(
        None, '--write-uuid', help='GATT write characteristic UUID (--transport ble)',
    ),
    notify_uuid: typing.Optional[str] = typer.Option(
        None, '--notify-uuid', help='GATT notify characteristic UUID (--transport ble, optional)',
    ),
    concentration: int = typer.Option(
        0, '--concentration', '-c', min=0, max=2, help='Print concentration/temperature (0-2)',
    ),
    break_size: int = typer.Option(
        0, '--break', '-b', min=0, max=255, help='Paper feed size after printing (0-255)',
    ),
    timeout: float = typer.Option(10.0, '--timeout', help='Connection timeout in seconds'),
    prefer_fast_write: bool = typer.Option(
        False, '--prefer-fast-write',
        help='(BLE) Use unacknowledged GATT writes when the characteristic supports both. '
             'Faster but no flow control - only enable if verified reliable on your device.',
    ),
    write_delay: float = typer.Option(
        0.0, '--write-delay',
        help='(BLE) Extra delay in seconds after each write chunk. Useful for diagnosing/working '
             'around printers whose feed motor stretches paper when their receive buffer starves.',
    ),
):
    """
    Set connection options once here, then pick a subcommand: text, stream,
    image, qr, or introduce. Example:

        peripage --printer P21 --transport ble --address AA:BB:CC:DD:EE:FF \\
            --write-uuid 0000ff02-... --notify-uuid 0000ff01-... \\
            text "hello"
    """

    # `discover` doesn't talk to a Printer at all - skip connecting.
    if ctx.invoked_subcommand == 'discover':
        return

    if printer is None:
        raise _fail('--printer / -p is required (except for the `discover` subcommand)')

    if printer not in PrinterType.names():
        raise _fail(f'Unknown --printer {printer!r}. Choices: {", ".join(PrinterType.names())}')

    xport = _build_transport(transport, mac, address, write_uuid, notify_uuid, timeout, prefer_fast_write, write_delay)
    p = Printer(xport, PrinterType[printer])

    typer.echo(f'Connecting ({transport}) ...')
    p.connect()
    p.reset()

    ctx.obj = ConnectionState(p, concentration, break_size)
    ctx.call_on_close(p.disconnect)


@app.command()
def introduce(ctx: typer.Context):
    """Ask the printer to introduce itself (device info string)."""

    state: ConnectionState = ctx.obj
    typer.echo(state.printer.getDeviceFull().decode('ascii', errors='replace'))


@app.command()
def text(
    ctx: typer.Context,
    text: str = typer.Argument(..., help='Text to print'),
    font_size: int = typer.Option(32, '--font-size', help='Font size (only used on printers with no onboard font, e.g. P21)'),
    align: str = typer.Option('left', '--align', help='"left", "center", or "right" (only used on printers with no onboard font)'),
):
    """
    Print a block of text. Automatically renders to an image on printers
    with no onboard font (e.g. the P21) - see `peripage.Printer.printText()`.
    """

    state: ConnectionState = ctx.obj
    state.printer.setConcentration(state.concentration)

    stripped = text.rstrip()
    if stripped:
        state.printer.printText(stripped, font_size=font_size, align=align)

    if state.break_size > 0:
        state.printer.printBreak(state.break_size)


@app.command()
def stream(
    ctx: typer.Context,
    font_size: int = typer.Option(32, '--font-size', help='Font size (only used on printers with no onboard font, e.g. P21)'),
    align: str = typer.Option('left', '--align', help='"left", "center", or "right" (only used on printers with no onboard font)'),
):
    """Print text from STDIN until EOF (Ctrl+D). Automatically renders to an
    image on printers with no onboard font (e.g. the P21)."""

    state: ConnectionState = ctx.obj
    state.printer.setConcentration(state.concentration)

    if state.printer.printer_type.spec.has_onboard_font:
        # Onboard-font printers can stream line by line, exactly like the
        # original implementation.
        while True:
            try:
                line = input().rstrip()
                state.printer.printlnASCII(line)
            except EOFError:
                break
    else:
        # No onboard font: rendering each line as a separate image would
        # be wasteful and would lose paragraph-level word wrap, so buffer
        # everything and render it as one block at EOF instead.
        lines = []
        while True:
            try:
                lines.append(input())
            except EOFError:
                break
        text_block = '\n'.join(lines).rstrip()
        if text_block:
            state.printer.printText(text_block, font_size=font_size, align=align)

    if state.break_size > 0:
        state.printer.printBreak(state.break_size)


@app.command()
def image(
    ctx: typer.Context,
    path: str = typer.Argument(..., help='Path to the image file to print'),
):
    """Print an image file."""

    import PIL.Image

    state: ConnectionState = ctx.obj
    state.printer.setConcentration(state.concentration)

    try:
        img = PIL.Image.open(path)
    except Exception as e:
        raise _fail(f'Failed to open image {path}: {e}')

    state.printer.printImage(img)

    if state.break_size > 0:
        state.printer.printBreak(state.break_size)


@app.command()
def qr(
    ctx: typer.Context,
    data: str = typer.Argument(..., help='Text/URL to encode as a QR code'),
):
    """Print a QR code."""

    state: ConnectionState = ctx.obj
    state.printer.setConcentration(state.concentration)
    state.printer.printQR(data)

    if state.break_size > 0:
        state.printer.printBreak(state.break_size)


@app.command()
def feed(
    ctx: typer.Context,
    size: int = typer.Option(None, '--size', min=1, max=255, help='Override the global --break size for this feed'),
):
    """Just feed some blank paper (handy for testing a connection)."""

    state: ConnectionState = ctx.obj
    state.printer.printBreak(size if size is not None else (state.break_size or 0x40))


# -- discover subcommands (no printer connection needed) --------------------

@discover_app.command('scan')
def discover_scan(
    timeout: float = typer.Option(5.0, '--timeout', help='Scan duration in seconds'),
):
    """Scan for nearby BLE devices and print their addresses/names."""

    from peripage.transport.ble_discover import run_scan
    run_scan(timeout)


@discover_app.command('services')
def discover_services(
    address: str = typer.Argument(..., help='BLE address from `discover scan`'),
    timeout: float = typer.Option(10.0, '--timeout', help='Connect timeout in seconds'),
):
    """Connect to a BLE device and list its GATT services/characteristics."""

    from peripage.transport.ble_discover import run_services
    run_services(address, timeout)


def main():
    app()


if __name__ == '__main__':
    main()
