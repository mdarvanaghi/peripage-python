# peripage-python - Home Assistant MQTT daemon
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

"""
Home Assistant MQTT Discovery + topic wiring for a single peripage printer,
backed by a `print_service.PrintService` job queue.

Entities exposed: a `text` entity to submit text-to-print, a `sensor` for
battery level, and a `button` to feed some blank paper. Availability uses the
standard per-entity `availability_topic`/LWT mechanism (grey-out in the HA
UI) rather than a dedicated visible entity.

Image printing is out of scope for now - there is no native HA MQTT entity
for "attach an image and print it".
"""

import json
import logging
import typing

from config import Config

logger = logging.getLogger(__name__)


class HaMqttBridge:
    def __init__(self, cfg: Config, service, client):
        """
        Arguments:
        * `cfg` - resolved `Config`.
        * `service` - a started `print_service.PrintService` instance.
        * `client` - a `paho.mqtt.client.Client`, not yet connected. This
          class assigns `on_connect`/`on_message` on it and configures its
          LWT (`will_set`) - do this before calling `client.connect()`.
        """

        self.cfg = cfg
        self.service = service
        self.client = client

        prefix = cfg.ha_discovery_prefix
        node = cfg.ha_node_id

        self.status_topic = f'{prefix}/{node}/status'
        self.battery_state_topic = f'{prefix}/{node}/battery/state'
        self.print_text_command_topic = f'{prefix}/{node}/print_text/set'
        self.print_text_state_topic = f'{prefix}/{node}/print_text/state'
        self.feed_command_topic = f'{prefix}/{node}/feed/set'

        self.discovery_topics = {
            f'{prefix}/text/{node}/print_text/config': self._text_discovery_payload(),
            f'{prefix}/sensor/{node}/battery/config': self._battery_discovery_payload(),
            f'{prefix}/button/{node}/feed/config': self._feed_discovery_payload(),
        }

        client.will_set(self.status_topic, payload='offline', retain=True)
        client.on_connect = self._on_connect
        client.on_message = self._on_message

    # -- discovery payloads ---------------------------------------------------

    def _device_block(self) -> dict:
        node = self.cfg.ha_node_id
        return {
            'identifiers': [f'peripage_{node}'],
            'name': self.cfg.ha_device_name,
            'manufacturer': 'PeriPage',
            'model': self.cfg.printer_type,
        }

    def _text_discovery_payload(self) -> dict:
        return {
            'name': 'Print text',
            'unique_id': f'peripage_{self.cfg.ha_node_id}_print_text',
            'command_topic': self.print_text_command_topic,
            'state_topic': self.print_text_state_topic,
            'availability_topic': self.status_topic,
            'payload_available': 'online',
            'payload_not_available': 'offline',
            'device': self._device_block(),
        }

    def _battery_discovery_payload(self) -> dict:
        return {
            'name': 'Battery',
            'unique_id': f'peripage_{self.cfg.ha_node_id}_battery',
            'state_topic': self.battery_state_topic,
            'unit_of_measurement': '%',
            'device_class': 'battery',
            'availability_topic': self.status_topic,
            'payload_available': 'online',
            'payload_not_available': 'offline',
            'device': self._device_block(),
        }

    def _feed_discovery_payload(self) -> dict:
        return {
            'name': 'Feed',
            'unique_id': f'peripage_{self.cfg.ha_node_id}_feed',
            'command_topic': self.feed_command_topic,
            'payload_press': 'PRESS',
            'availability_topic': self.status_topic,
            'payload_available': 'online',
            'payload_not_available': 'offline',
            'device': self._device_block(),
        }

    def publish_discovery(self) -> None:
        for topic, payload in self.discovery_topics.items():
            self.client.publish(topic, json.dumps(payload), retain=True)

    # -- mqtt callbacks ---------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            logger.error('MQTT connect failed with rc=%s', rc)
            return

        client.subscribe(self.print_text_command_topic)
        client.subscribe(self.feed_command_topic)
        self.publish_discovery()
        client.publish(self.status_topic, 'online', retain=True)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            if msg.topic == self.print_text_command_topic:
                self._handle_print_text(msg.payload)
            elif msg.topic == self.feed_command_topic:
                self._handle_feed()
        except Exception:
            logger.exception('Failed to handle MQTT message on topic %s', msg.topic)

    # -- command handlers ---------------------------------------------------------

    def _handle_print_text(self, payload: bytes) -> None:
        text = payload.decode('utf-8', errors='replace')

        from peripage import PrinterType

        printer_type = PrinterType[self.cfg.printer_type]
        if printer_type.spec.has_onboard_font:
            self.service.add_print_ascii(text, self.cfg.concentration, self.cfg.break_size, flush=True)
        else:
            font_size = self.cfg.font_size
            align = self.cfg.align
            break_size = self.cfg.break_size
            concentration = self.cfg.concentration

            def wrap_print_text(printer):
                printer.setConcentration(concentration)
                stripped = text.rstrip()
                if stripped:
                    printer.printText(stripped, font_size=font_size, align=align)
                if break_size > 0:
                    printer.printBreak(break_size)

            self.service.add_print_handler(wrap_print_text)

        self.client.publish(self.print_text_state_topic, text, retain=True)

    def _handle_feed(self) -> None:
        self.service.add_print_break(self.cfg.break_size or 0x40)

    # -- telemetry ---------------------------------------------------------

    def publish_battery(self, value: int) -> None:
        self.client.publish(self.battery_state_topic, str(value))

    def publish_offline(self) -> None:
        self.client.publish(self.status_topic, 'offline', retain=True)
