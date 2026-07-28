import typer
from typing import Optional
from PIL import Image
import peripage

app = typer.Typer(
    name="peripage",
    help="Print on a Peripage printer via BLE (Bluetooth Low Energy).",
    add_completion=False,
)


@app.command()
def text(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    text: str = typer.Option(..., "--text", "-t", help="ASCII text to print"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    transport: str = typer.Option("classic", "--transport", "-tr", help="Transport type",
                                choices=["classic", "ble"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Print ASCII text."""
    printer_obj = peripage.Printer(
        mac,
        getattr(peripage.PrinterType, printer.upper()),
        transport_type=transport
    )
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)
    printer_obj.printASCII(text)
    printer_obj.flushASCII()

    if break_size > 0:
        printer_obj.printBreak(break_size)

    printer_obj.disconnect()


@app.command()
def image(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    image_path: str = typer.Option(..., "--image", "-i", help="Path to the image file"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    concentration: int = typer.Option(0, "--concentration", "-c", help="Concentration value (0-2)",
                                    min=0, max=2),
    break_size: int = typer.Option(0, "--break", "-b", help="Break size after printing (0-255)",
                                 min=0, max=255),
):
    """Print an image file."""
    printer_obj = peripage.Printer(mac, getattr(peripage.PrinterType, printer.upper()))
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)

    try:
        img = Image.open(image_path)
        printer_obj.printImage(img)
    except Exception as e:
        typer.echo(f"Error opening image: {e}", err=True)
        raise typer.Exit(1)

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
    printer_obj = peripage.Printer(mac, getattr(peripage.PrinterType, printer.upper()))
    printer_obj.connect()
    printer_obj.reset()

    printer_obj.setConcentration(concentration)
    printer_obj.printQR(text)

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
    printer_obj = peripage.Printer(mac, getattr(peripage.PrinterType, printer.upper()))
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
def introduce(
    mac: str = typer.Option(..., "--mac", "-m", help="Bluetooth MAC address of the printer"),
    printer: str = typer.Option(..., "--printer", "-p", help="Printer model",
                               choices=["A6", "A6p", "A40", "A40p"]),
    transport: str = typer.Option("classic", "--transport", "-tr", help="Transport type",
                                choices=["classic", "ble"]),
):
    """Ask the printer to introduce itself and print the response."""
    printer_obj = peripage.Printer(
        mac,
        getattr(peripage.PrinterType, printer.upper()),
        transport_type=transport
    )
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