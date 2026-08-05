# peripage-python
### Python module for printing on Peripage printers

**This project is a continued development of the [original project](https://github.com/eliasweingaertner/peripage-A6-bluetooth) made by [Elias Weingärtner](https://github.com/eliasweingaertner). This module combined all results of reverse engineering of the Peripage A6/A6+ protocol in a python utility providing interface and CLI tool for printing on this thermal printer.**

This module supports two transports: classic Bluetooth (RFCOMM/SPP, via `PyBluez`) for the A6/A6+/A40/A40+, and BLE (via `bleak`) for the P21. Both are driven through the same protocol implementation via a pluggable `Transport` interface - see [Transports](#transports) below.

## [The original introduction](https://github.com/eliasweingaertner/peripage-A6-bluetooth#introduction)

The Peripage A6 F622 is an inexpensive portable thermal printer. It provides both Bluetooth and USB connectivity. Unlike most other thermo printers it **does not** seem to support ESC/POS or any other standardized printer control language.

So far, the Peripage A6 F622 can be only controlled using a proprietary app (iOS / Anndroid). There is also a driver for Windows with many limitations, most notably the need of defining a page size before printing; this is a huge limitation, as the Peripage prints on continuous form paper.

The script provided here was built based on an analysis of captured Bluetooth traffic between the printer and an Android device. The Peripage A6 uses the serial profile (BTSPP) and RFCOMM.

Essentially, the script takes an input images, scales it to the printers native X resolution of 384 pixels, and then sends it to the printer.

## Deprecation Warning

**The latest version ot `ppa6-python` module is deprecated due the major update with new models support and better module naming**

## Denial of responsibility

The author and people associated with him are not responsible for the inoperability, breakdown, disruption and failure of software and hardware, as well as loss and damage to physical and software property as a result of the use of this software and related projects. Everything you do is at your own risk and responsibility.

## Features

* Printing text of any length encoded in ASCII
* Printing Images using PIL library
* Printing Images row-by row using binary row representation
* Printing page breaks using paper feed
* Printing using generator/iterator that return bytes for each row, chunks of bytes for each row, images
* Requesting printer details (Serial Number, Name, Battery Level, Hardware Info and an option the meaning of which i don't know)
* Configuring print concentration (temperature)
* Changing printer serial number
* Configuring printer poweroff timeout
* Supported printers:
  * Peripage A6 (classic Bluetooth)
  * Peripage A6+ (classic Bluetooth)
  * Peripage A40 (classic Bluetooth)
  * Peripage A40+ (classic Bluetooth)
  * Peripage P21 (BLE, 57mm x 40mm paper)

## Prerequisites

* Peripage A6/A6+/A40/A40+/P21/e.t.c printer
* Python 3

## Installation

**Install from git clone**

```
# core only (Printer/protocol, no transport) - rarely what you want on its own
pip install -r requirements.txt
pip install . --user

# classic Bluetooth printers (A6/A6+/A40/A40+)
pip install -r requirements-classic.txt
pip install ".[classic]" --user

# BLE printers (P21)
pip install -r requirements-ble.txt
pip install ".[ble]" --user
```

**Install from pypi using pip**

```
pip install peripage[classic]   # A6/A6+/A40/A40+
pip install peripage[ble]       # P21
```

## Dependencies

Core (always required):
* `Pillow>=8.2.0`
* `qrcode>=6.1`
* `typer>=0.9.0` (CLI)

Transport-specific (only install what you need):
* `PyBluez>=0.23` - classic Bluetooth (A6/A6+/A40/A40+), via `requirements-classic.txt` / `pip install ".[classic]"`
* `bleak>=0.20.0` - BLE (P21), via `requirements-ble.txt` / `pip install ".[ble]"`

`PyBluez` has native build dependencies (see Troubleshooting below) - if you only have a BLE printer like the P21, you don't need it at all.

## Transports

This module talks to printers through a pluggable `Transport` interface (`peripage.transport.Transport`), with two built-in implementations:

* `SocketTransport` - classic Bluetooth (RFCOMM/SPP) via `PyBluez`. Used by the A6/A6+/A40/A40+.
* `BleakTransport` - Bluetooth Low Energy (GATT) via `bleak`. Used by the P21.

Both are driven by the exact same `Printer`/protocol code - only the way bytes physically get to the printer differs. This also means you can write your own `Transport` for other connection types (USB serial, a network bridge, etc.) without touching the protocol implementation at all.

### Classic Bluetooth (A6/A6+/A40/A40+)

**Identify printer Bluetooth MAC address**

**On linux:**

```
user@name:~$ hcitool scan
Scanning ..
00:15:83:15:bc:5f    PeriPage+BC5F
```

**On windows:**

You may use [BluetoothCL](https://www.nirsoft.net/utils/bluetoothcl.html)

```
PS E:\E\E> .\BluetoothCL.exe
BluetoothCL v1.07
Copyright (c) 2009 - 2014 Nir Sofer
Web Site: http://www.nirsoft.net

syntax:
BluetoothCL -timeout [seconds]

-timeout is optional parameter. The default value is 15 seconds.


Scanning bluetooth devices... please wait.

00:15:83:15:bc:5f    Imaging                         PeriPage+BC5F
```

```python
from peripage import Printer, PrinterType
from peripage.transport import SocketTransport

transport = SocketTransport('00:15:83:15:bc:5f', timeout=1.0)
printer = Printer(transport, PrinterType.A6p)
printer.connect()
printer.reset()
```

### BLE (P21)

BLE printers don't have a single fixed "channel" like classic Bluetooth's RFCOMM - you need the printer's address plus the GATT **write characteristic UUID** (and, if you want responses, the **notify characteristic UUID**). Find them with the built-in discovery command:

```
python -m peripage discover scan
python -m peripage discover services <address>
```

`scan` lists nearby BLE devices with their addresses/names. `services <address>` connects and dumps every GATT service/characteristic, flagging ones that look like write/notify candidates (look for a characteristic under a custom, non-standard service UUID with `write`/`write-without-response` in its properties for the write UUID, and one with `notify` for the notify UUID).

The address and UUIDs below are illustrative - discover the actual values for your specific unit as shown above.

```python
from peripage import Printer, PrinterType
from peripage.transport import BleakTransport

transport = BleakTransport(
    address='AA:BB:CC:DD:EE:FF',
    write_characteristic='0000ff02-0000-1000-8000-00805f9b34fb',
    notify_characteristic='0000ff01-0000-1000-8000-00805f9b34fb',
)
printer = Printer(transport, PrinterType.P21)
printer.connect()
printer.reset()
```

## Troubleshooting

> These PyBluez-related items only apply if you're using `SocketTransport` (classic Bluetooth: A6/A6+/A40/A40+). BLE printers like the P21 use `bleak` instead and don't need PyBluez at all.

> Windows installation requires installing PyBluez from master branch as pypi module is not updated

```
pip install git+https://github.com/pybluez/pybluez@master#egg=pybluez --user
```

> Raspberry PI installation requires additional libraries

```
sudo apt install libbluetooth-dev libopenjp2-7 libtiff5
```

> Some cases may require restarting bluetooth adapter

```
sudo systemctl restart bluetooth
sudo hciconfig hci0 reset
```

## CLI usage

**On linux**

Install module and run
`peripage <args>`

**On windows**

Install module and run
`python -m peripage <args>`

### Options

Connection options are set once via the main command, then a subcommand (`text`, `stream`, `image`, `qr`, `introduce`, `feed`) says what to actually print. `discover` is a separate subcommand group that doesn't need any connection options.

```
$ python -m peripage --help
Usage: peripage [OPTIONS] COMMAND [ARGS]...

  Print on a Peripage printer over classic Bluetooth (A6/A6+/A40/A40+) or
  BLE (P21).

Options:
  -p, --printer TEXT       Printer model. One of: A6, A6p, A40, A40p, P21
  --transport TEXT         "classic" (RFCOMM - A6/A6+/A40/A40+) or "ble"
                            (P21)  [default: ble]
  -m, --mac TEXT           Bluetooth MAC address (--transport classic)
  -a, --address TEXT       BLE device address (--transport ble)
  --write-uuid TEXT        GATT write characteristic UUID (--transport ble)
  --notify-uuid TEXT       GATT notify characteristic UUID (--transport
                            ble, optional)
  -c, --concentration INTEGER RANGE
                            Print concentration/temperature (0-2)
                            [default: 0]
  -b, --break INTEGER RANGE
                            Paper feed size after printing (0-255)
                            [default: 0]
  --timeout FLOAT           Connection timeout in seconds  [default: 10.0]
  --help                    Show this message and exit.

Commands:
  discover    Find a BLE printer's address and GATT characteristic UUIDs...
  feed        Just feed some blank paper (handy for testing a connection).
  image       Print an image file.
  introduce   Ask the printer to introduce itself (device info string).
  qr          Print a QR code.
  stream      Print text from STDIN, line by line, until EOF (Ctrl+D).
  text        Print a block of ASCII text.
```

### Discover a BLE printer (P21)

```
python -m peripage discover scan
python -m peripage discover services <address>
```

### Print image example

**Print image from [file](https://github.com/bitrate16/peripage-python/blob/main/honk.png) with following break for 100px and concentration set to 2 (HIGH) on A6+ (classic Bluetooth)**
```
peripage -p A6p --transport classic -m 00:15:83:15:bc:5f -b 100 -c 2 image honk.png
```

**Same, on a P21 over BLE**
```
peripage -p P21 --transport ble -a AA:BB:CC:DD:EE:FF --write-uuid 0000ff02-0000-1000-8000-00805f9b34fb --notify-uuid 0000ff01-0000-1000-8000-00805f9b34fb --prefer-fast-write -b 80 -c 2 image honk.png
```

### Print text example

**Print some random text followed by newline and break for 100px on A6+**
```
peripage -p A6p --transport classic -m 00:15:83:15:bc:5f -b 100 text "HONK"
```

**Same, on a P21 over BLE** - the P21 has no onboard font (see [Recommendations](#recommendations)), so `text` automatically renders to an image behind the scenes instead. `--font-size` and `--align` only affect this rendering path:
```
peripage -p P21 --transport ble -a AA:BB:CC:DD:EE:FF --write-uuid 0000ff02-0000-1000-8000-00805f9b34fb --notify-uuid 0000ff01-0000-1000-8000-00805f9b34fb --prefer-fast-write -b 80 text --font-size 28 --align center "HONK"
```

### Print QR code example

```
peripage -p P21 --transport ble -a AA:BB:CC:DD:EE:FF --write-uuid 0000ff02-0000-1000-8000-00805f9b34fb --notify-uuid 0000ff01-0000-1000-8000-00805f9b34fb --prefer-fast-write -b 80 qr "https://example.com"
```

### Create ruler example

This will generate an image of ruler, approximately matching real centimeters (measured with unpreciese real ruler) on Periapge A6+

```python

WIDTH = 576
WIDTH_MM = 48.5
MM2PX = WIDTH / WIDTH_MM
CM2PX = 10 * MM2PX
TICKS = 100
TICK_HEIGHT = 4
TICK_WIDTH = 50


import PIL
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont


image = PIL.Image.new('RGB', (WIDTH, int(MM2PX * 10 * (TICKS + 2))), (255, 255, 255))
draw = PIL.ImageDraw.Draw(image)
# font = PIL.ImageFont.truetype('/usr/share/fonts/gnu-free/FreeSans.ttf', 18)
font = PIL.ImageFont.truetype('/usr/share/fonts/open-sans/OpenSans-Regular.ttf', 40)

for tick in range(1, TICKS + 2):
    for ty in range(TICK_HEIGHT):
        for tx in range(TICK_WIDTH):
            image.putpixel(
                (
                    int(tx),
                    int(tick * CM2PX + ty),
                ),
                (0, 0, 0),
            )

        draw.text(
            (
                int(TICK_WIDTH * 2),
                int(tick * CM2PX - 0.25 * CM2PX + ty),
            ),
            text=str(tick - 1),
            font=font,
            fill='black',
        )


image.save('ruler.png')

```

## Home Assistant

For a printer wired into Home Assistant (auto-discovered, no manual entity
config) rather than driven from scripts, see [`ha-mqtt-daemon/`](ha-mqtt-daemon/README.md) -
a long-running daemon that auto-discovers a BLE printer (P21), registers
itself with HA via MQTT Discovery, and exposes a text-to-print entity,
battery sensor, and feed button. Includes a one-line installer
(`curl ... | sudo bash`) that sets it up as a systemd service.

## Print Service

**Print 50 text tasks on A6+ (classic Bluetooth)**
```python
import peripage
from peripage.transport import SocketTransport
import print_service

# Ping battery every 60 seconds
# Send task every 5 seconds
# Try to reconnect after waiting 5 seconds
# Wait 1 second before send after connecting/reconnecting to printer
# Print only after pinging printer and waiting for 1 second
service = print_service.PrintService(60, 5, 5, 1, 1)
service.start(SocketTransport('00:15:83:15:bc:5f', timeout=1.0), peripage.PrinterType.A6p)
for i in range(50):
	service.add_print_ascii(f'number {i}', flush=True)
```
Newline is required to fush the internal printer buffer and force it to print all text without cutting

**Same, on a P21 over BLE**
```python
import peripage
from peripage.transport import BleakTransport
import print_service

service = print_service.PrintService(60, 5, 5, 1, 1)
transport = BleakTransport(
	address='AA:BB:CC:DD:EE:FF',
	write_characteristic='0000ff02-0000-1000-8000-00805f9b34fb',
	notify_characteristic='0000ff01-0000-1000-8000-00805f9b34fb',
	prefer_fast_write=True,  # recommended for the P21, see Recommendations
)
service.start(transport, peripage.PrinterType.P21)
for i in range(50):
	service.add_print_handler(lambda printer, i=i: printer.printText(f'number {i}'))
```
`printer.printText()` automatically renders to an image on the P21 (no onboard font - see [Recommendations](#recommendations)) and sends raw ASCII directly on printers that do have one, so the same call works unmodified on either transport.

## Recommendations

* Don't forget about concentration, this can make print brighter and better visible.
* Split long images into multiple print requests with cooldown time for printer (printer may overheat during a long print and will stop printing for a while. This will result in partial print loss because the internal buffer is about 250px height). For example, when you print [looooooooooooooooooooooooooooooongcat.jpg](http://lurkmore.so/images/9/91/Loooooooooooooooooooooooooooooooooooooooooongcat.JPG), split it into at least 20 pieces with 1-2 minutes delay because you will definetly loose something without cooling. Printer gets hot very fast. Yes, it was the first that i've printed.
* Be carefull when printing lots of black or using max concentration, as i said, printer heats up very fast.
* The picture printed at maximum concentration has the longest shelf life.
* Turn printer off then long press the power button till it becomes orange. Release the button and look at the another useless feature.
* Be aware of cats, they have paws 🐾
* **BLE printers may have no onboard ASCII font.** Raw ASCII passthrough (`printASCII`/`flushASCII`) relies on the printer's firmware to rasterize it, which BLE "cat printer"-style devices (like the P21) generally don't support - they only print bitmaps. `Printer.printText()` (and the CLI's `text`/`stream` commands) handle this automatically via the `has_onboard_font` flag on `PrinterTypeSpecs`: `True` sends raw ASCII as before; `False` renders the text to an image with a bundled monospace font (`peripage/text_render.py`, word-wrapped to the printer's dot width) and prints that instead. This also means Unicode, custom font sizes, and alignment all work on printers without onboard fonts.
* **BLE write throughput matters for print quality, not just speed.** `BleakTransport` batches consecutive small writes into full-MTU chunks rather than issuing one GATT write per printed row, since BLE's ATT layer only allows one pending Write Request/Response at a time. It defaults to acknowledged writes (`response=True`) for flow control - unacknowledged writes can silently drop data if sent faster than the printer's BLE stack can drain it, corrupting the print. `prefer_fast_write=True` (`--prefer-fast-write` on the CLI) switches to unacknowledged writes for lower latency; only enable it after confirming reliability with several repeated prints on your specific device, since printers vary in how much backpressure they need.
* **Calibrate transport throughput before calibrating geometry.** `PrinterTypeSpecs.aspect_correction` compensates for a mismatch between a printer's paper-feed distance per row and its horizontal dot pitch. If write throughput can't keep up with the printer's internal draw rate, its feed motor can stretch paper while starved for data - which looks identical to a geometry mismatch but isn't one, and will corrupt your calibration if measured first. Tune transport settings (batching, `prefer_fast_write`) for reliable, evenly-paced output first, then calibrate `aspect_correction` against that configuration using `scripts/print_bar.py`.

## Code example

View this [python notebook](https://github.com/bitrate16/peripage-python/blob/main/notebooks/peripage-tutorial.ipynb) for tutorial

View this [python notebook](https://github.com/bitrate16/peripage-python/blob/main/notebooks/Test-notebook.ipynb) for test

## Printer disassembly

[Disassembly for A6+](https://imgur.com/a/6LLwuaD)

## TODO

* Fix page sometimes get cutted off for some rows
* Fix delays
* ~~Python 2.7 support~~ (Don't need)
* Implement overheat protection
* Implement cover open handler
* Tweak wait timings to precisely match printing speed
* Implement printer renaming
* Implement printing stop operation
* Reverse-engineer USB driver and add support for it
* Print randomly gets cropped (some images getting cropped)
* 1 type conversion is low quality

## Contribution

> Q: How to contribute?
>
> A: Implement some features and make a pull request in this repo. For example, you could add info about USB communication, make an additional research in protocol and other cool things.

> Q: How to get my printer supported?
>
> A: If you own a peripage printer that is currently unsupported, you can reverse-engineer the bluetooth packets captured from the oficial printing app and find out the specs of your printer (the main and the only spec is bytes per row). Another way is to find how many letters can fit in a row when using `printASCII()`.
>
> If you would like to participate, please make an issue and I will guide you on how to obtain required parameters.

## Credits

* [Elias Weingärtner](https://github.com/eliasweingaertner) for initial work in reverse-engineering bluetooth protocol
* [bitrate16](https://github.com/bitrate16) for additional research and python module
* [henryleonard](https://github.com/henryleonard) for specs of A40 printer
* [anthony-foulfoin](https://github.com/anthony-foulfoin) for specs of A40+ printer

## License

[GPLv3 License](https://github.com/bitrate16/peripage-python/blob/main/LICENSE)
