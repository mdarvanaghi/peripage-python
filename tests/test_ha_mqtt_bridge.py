# peripage-python - Home Assistant MQTT daemon tests
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# Verifies ha-mqtt-daemon/mqtt_bridge.py's on_message dispatch against a real
# PrintService backed by FakeTransport (no hardware, no real MQTT broker) -
# and a fake paho.mqtt.client.Client stand-in to capture what would have
# been published.

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ha-mqtt-daemon'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'print-server'))

from peripage import PrinterType
from peripage.transport.fake_transport import FakeTransport
import print_service

import config as config_module
import mqtt_bridge


class FakeMqttMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class FakeMqttClient:
    def __init__(self):
        self.published = []  # list of (topic, payload, retain)
        self.subscribed = []
        self.on_connect = None
        self.on_message = None
        self._will = None

    def will_set(self, topic, payload=None, retain=False):
        self._will = (topic, payload, retain)

    def subscribe(self, topic):
        self.subscribed.append(topic)

    def publish(self, topic, payload=None, retain=False):
        self.published.append((topic, payload, retain))

    def last_payload(self, topic):
        for t, p, _ in reversed(self.published):
            if t == topic:
                return p
        return None


def _make_config(printer_type: str) -> config_module.Config:
    os.environ['PRINTER_TYPE'] = printer_type
    os.environ['PRINTER_TRANSPORT'] = 'ble'
    os.environ['PRINTER_BLE_ADDRESS'] = 'AA:BB:CC:DD:EE:FF'
    os.environ['PRINTER_BLE_WRITE_UUID'] = 'write-uuid'
    cfg = config_module.Config.from_env()
    for key in ('PRINTER_TYPE', 'PRINTER_TRANSPORT', 'PRINTER_BLE_ADDRESS', 'PRINTER_BLE_WRITE_UUID'):
        del os.environ[key]
    return cfg


def _start_service(printer_type: PrinterType) -> print_service.PrintService:
    transport = FakeTransport()
    service = print_service.PrintService(
        ping_interval=9999,
        event_interval=0.05,
        offline_interval=0.05,
        startup_interval=0,
        guard_ping_interval=None,
    )
    service.start(transport, printer_type, concentration=0)

    deadline = time.time() + 3.0
    while not transport.is_connected() and time.time() < deadline:
        time.sleep(0.05)

    return service


def _drain(service: print_service.PrintService):
    deadline = time.time() + 3.0
    while service.get_task_count() > 0 and time.time() < deadline:
        time.sleep(0.05)


def test_print_text_on_onboard_font_printer_uses_ascii():
    cfg = _make_config('A6p')
    service = _start_service(PrinterType.A6p)
    client = FakeMqttClient()
    bridge = mqtt_bridge.HaMqttBridge(cfg, service, client)

    bridge._on_message(client, None, FakeMqttMessage(bridge.print_text_command_topic, b'hello'))
    _drain(service)

    assert b'hello' in service.printer.transport.all_sent()
    assert client.last_payload(bridge.print_text_state_topic) == 'hello'

    service.stop()


def test_print_text_on_no_onboard_font_printer_uses_print_text():
    cfg = _make_config('P21')
    service = _start_service(PrinterType.P21)
    client = FakeMqttClient()
    bridge = mqtt_bridge.HaMqttBridge(cfg, service, client)

    bridge._on_message(client, None, FakeMqttMessage(bridge.print_text_command_topic, b'hello'))
    _drain(service)

    # P21 has no onboard font - text is rendered to an image, so the raw
    # ASCII bytes should NOT appear verbatim on the wire.
    assert b'hello' not in service.printer.transport.all_sent()
    assert len(service.printer.transport.sent) > 0
    assert client.last_payload(bridge.print_text_state_topic) == 'hello'

    service.stop()


def test_feed_command_triggers_break():
    cfg = _make_config('A6p')
    service = _start_service(PrinterType.A6p)
    client = FakeMqttClient()
    bridge = mqtt_bridge.HaMqttBridge(cfg, service, client)

    sent_before = len(service.printer.transport.sent)
    bridge._on_message(client, None, FakeMqttMessage(bridge.feed_command_topic, b'PRESS'))
    _drain(service)

    assert len(service.printer.transport.sent) > sent_before

    service.stop()


def test_on_connect_publishes_discovery_and_subscribes():
    cfg = _make_config('A6p')
    service = _start_service(PrinterType.A6p)
    client = FakeMqttClient()
    bridge = mqtt_bridge.HaMqttBridge(cfg, service, client)

    bridge._on_connect(client, None, None, 0)

    assert bridge.print_text_command_topic in client.subscribed
    assert bridge.feed_command_topic in client.subscribed
    assert client.last_payload(bridge.status_topic) == 'online'
    discovery_topics = {t for t, _, _ in client.published if '/config' in t}
    assert len(discovery_topics) == 3

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
