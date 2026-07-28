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

import typer
from typing import Optional
from PIL import Image

from . import *
from .transport import BleakTransport

app = typer.Typer(help="Print on a Peripage printer via BLE (Bluetooth Low Energy)")


def get_printer(mac: str, printer: str) -> "Printer":
    """Get a Printer instance."""
    printer_enum = getattr(PrinterType, printer.upper())
    return Printer(mac, printer_enum)


@app.command()
def text(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    text: str = typer.Option(..., "--text", "-t", help="ASCII text to print"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Print ASCII text."""
    printer_obj = get_printer(mac, printer)
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)

    if text:
        printer_obj.printASCII(text)
        printer_obj.flushASCII()

    if break_size > 0:
        printer_obj.printBreak(break_size)

    printer_obj.disconnect()


@app.command()
def stream(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Read text from stdin and print it line by line."""
    printer_obj = get_printer(mac, printer)
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)

    try:
        while True:
            try:
                line = input().rstrip()
                printer_obj.printlnASCII(line)
            except EOFError:
                break
    except KeyboardInterrupt:
        typer.echo("\nInterrupted", err=True)

    if break_size > 0:
        printer_obj.printBreak(break_size)

    printer_obj.disconnect()


@app.command()
def image(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    image_path: str = typer.Option(..., "--image", "-i", help="Path to the image for printing"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    transport: str = typer.Option("classic", "--transport", "-tr", help="Transport type",
                                choices=["classic", "ble"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Print an image file."""
    printer_obj = get_printer(mac, printer, transport)
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)

    try:
        img = Image.open(image_path)
    except Exception as e:
        typer.echo(f"Error opening image: {e}", err=True)
        raise typer.Exit(1)

    printer_obj.printImage(img)

    if break_size > 0:
        printer_obj.printBreak(break_size)

    printer_obj.disconnect()


@app.command()
def qr(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    text: str = typer.Option(..., "--text", "-t", help="Text to encode in QR code"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Print a QR code."""
    printer_obj = get_printer(mac, printer)
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)
    printer_obj.printQR(text)

    if break_size > 0:
        printer_obj.printBreak(break_size)

    printer_obj.disconnect()


@app.command()
def introduce(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Ask the printer to introduce itself and print the response."""
    printer_obj = get_printer(mac, printer)
    printer_obj.connect()
    printer_obj.reset()

    try:
        response = printer_obj.getDeviceFull()
        typer.echo(response.decode('ascii'))
    except Exception as e:
        typer.echo(f"Error getting device info: {e}", err=True)
        raise typer.Exit(1)

    printer_obj.disconnect()


if __name__ == "__main__":
    app()