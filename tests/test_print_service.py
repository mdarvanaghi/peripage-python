# peripage-python - python library for peripage thermal printers
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# Verifies print_service.PrintService still works after porting it from the
# old socket-coupled Printer(mac, type, timeout) API to the new
# Printer(transport, type) API. No hardware needed - FakeTransport stands
# in for a real connection.

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage import PrinterType
from peripage.transport.fake_transport import FakeTransport
import print_service


def test_service_connects_and_processes_a_task():
    transport = FakeTransport()
    service = print_service.PrintService(
        ping_interval=9999,   # keep it out of the way for this test
        event_interval=0.05,
        offline_interval=0.05,
        startup_interval=0,
        guard_ping_interval=None,
    )

    service.start(transport, PrinterType.A6, concentration=0)

    got_text = []
    service.add_print_handler(lambda p: got_text.append('ran'))

    # Give the background thread a few ticks to connect and process the task.
    deadline = time.time() + 3.0
    while service.get_task_count() > 0 and time.time() < deadline:
        time.sleep(0.05)

    service.stop()

    assert transport.is_connected() is False  # stop() disconnects
    assert got_text == ['ran'], f'expected task to run exactly once, got {got_text}'
    assert service.get_task_count() == 0


def test_service_uses_configured_printer_type():
    transport = FakeTransport()
    service = print_service.PrintService(event_interval=0.05, startup_interval=0, guard_ping_interval=None)
    service.start(transport, PrinterType.P21, concentration=1)

    deadline = time.time() + 2.0
    while not transport.is_connected() and time.time() < deadline:
        time.sleep(0.05)

    assert service.printer.printer_type == PrinterType.P21
    service.stop()


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    sys.exit(1 if failed else 0)
