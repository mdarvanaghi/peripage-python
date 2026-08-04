# peripage-python - python library for peripage thermal printers
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# Milestone 1 verification: the protocol extraction must send byte-for-byte
# the same opcodes the original peripage.py did, just routed through a
# Transport instead of a raw PyBluez socket. No physical printer is needed
# for this - it substitutes a FakeTransport and inspects exactly what
# would have gone over the wire.

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage.protocol import Printer, PrinterType
from peripage.transport.fake_transport import FakeTransport


def make_printer(printer_type=PrinterType.A6):
    transport = FakeTransport()
    printer = Printer(transport, printer_type)
    printer.connect()
    return printer, transport


def test_connect_delegates_to_transport():
    printer, transport = make_printer()
    assert transport.connected is True
    assert printer.isConnected() is True


def test_reset_opcode_unchanged():
    printer, transport = make_printer()
    printer.reset()
    assert transport.last_sent() == bytes.fromhex('10fffe01000000000000000000000000')


def test_print_break_opcode_unchanged():
    printer, transport = make_printer()
    printer.printBreak(0x30)
    assert transport.last_sent() == bytes.fromhex('1b4a30')


def test_get_device_name_roundtrip():
    printer, transport = make_printer()
    transport.queue_response(b'PeriPage+DF7A')
    result = printer.getDeviceName()
    assert transport.last_sent() == bytes.fromhex('10ff3011')
    assert result == b'PeriPage+DF7A'


def test_get_device_battery_parses_second_byte():
    printer, transport = make_printer()
    transport.queue_response(bytes([0, 64]))
    assert printer.getDeviceBattery() == 64


def test_set_concentration_opcodes():
    printer, transport = make_printer()

    printer.setConcentration(0, wait=False)
    assert transport.last_sent() == bytes.fromhex('10ff100000')

    printer.setConcentration(1, wait=False)
    assert transport.last_sent() == bytes.fromhex('10ff100001')

    printer.setConcentration(2, wait=False)
    assert transport.last_sent() == bytes.fromhex('10ff100002')


def test_print_row_preamble_and_padding():
    printer, transport = make_printer(PrinterType.A6)
    printer.printRow(b'\xff' * 4)

    sent = transport.all_sent()
    # reset() opcode, followed by the row preamble + padded row
    expected_row = b'\xff' * 4 + b'\x00' * (printer.getRowBytes() - 4)
    expected_preamble = bytes.fromhex('1d763000') + bytes([printer.getRowBytes()]) + bytes.fromhex('000100')
    assert sent == bytes.fromhex('10fffe01000000000000000000000000') + expected_preamble + expected_row


def test_p21_printer_type_registered():
    assert 'P21' in PrinterType.names()
    assert PrinterType.P21.spec.row_bytes > 0
    assert PrinterType.P21.spec.row_width > 0
    assert PrinterType.P21.spec.row_characters > 0


def test_printascii_filters_and_wraps():
    printer, transport = make_printer(PrinterType.A6)
    printer.printASCII('hi')
    printer.flushASCII()
    assert transport.all_sent() == b'hi\n'


def test_p21_aspect_correction_shrinks_row_count():
    import PIL.Image

    printer_uncorrected, transport_uncorrected = make_printer(PrinterType.A6)  # aspect_correction=1.0
    printer_corrected, transport_corrected = make_printer(PrinterType.P21)     # aspect_correction=48/65

    square = PIL.Image.new('L', (100, 100), color=255)

    printer_uncorrected.printImage(square)
    printer_corrected.printImage(square)

    rows_uncorrected = len(transport_uncorrected.sent) - 1  # minus the reset() call
    rows_corrected = len(transport_corrected.sent) - 1

    assert rows_corrected < rows_uncorrected
    expected_ratio = PrinterType.P21.spec.aspect_correction
    assert abs(rows_corrected / rows_uncorrected - expected_ratio) < 0.05


def test_printtext_uses_raw_ascii_when_onboard_font_available():
    printer, transport = make_printer(PrinterType.A6)  # has_onboard_font=True
    printer.printText('hello')
    # same wire format as printASCII()+flushASCII(): raw bytes, trailing newline
    assert transport.all_sent() == b'hello\n'


def test_printtext_renders_image_when_no_onboard_font():
    printer, transport = make_printer(PrinterType.P21)  # has_onboard_font=False
    printer.printText('hello p21')

    sent = transport.all_sent()
    # should NOT be raw ASCII passthrough
    assert b'hello p21' not in sent
    # should look like image-row opcodes instead (same preamble printImage uses)
    assert bytes.fromhex('1d763000') in sent
    # more than just the reset() opcode was sent - actual row data went out
    assert len(transport.sent) > 2


def test_printtext_respects_printer_type():
    p21_printer, p21_transport = make_printer(PrinterType.P21)
    a6_printer, a6_transport = make_printer(PrinterType.A6)

    p21_printer.printText('x')
    a6_printer.printText('x')

    # A6 (onboard font): tiny raw payload
    assert len(a6_transport.all_sent()) < 10
    # P21 (rendered image): substantially larger payload for the same text
    assert len(p21_transport.all_sent()) > len(a6_transport.all_sent())


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    sys.exit(1 if failed else 0)
