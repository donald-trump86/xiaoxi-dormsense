"""Offline YAML/guard-text contracts, NOT Home Assistant template rendering.

No broker fixtures, template interpreter, HA access, or network operations.
Actual rendering, entity IDs, unchanged-value updates and expiry need HA tests.
"""

import hashlib
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "home-assistant/mqtt/real/node01.yaml"
LEGACY = ROOT / "home-assistant" / "mqtt" / "sensors.yaml"
LEGACY_SHA256 = "1a9548e31770e1f8af1f6e1e49bfe5639055a37a77e05ed1aecf823b827265fa"
TELEMETRY = "xiaoxi/validated/node01/telemetry"
STATUS = "xiaoxi/validated/node01/status"
CHANNELS = {"temperature": "°C", "humidity": "%", "light": None}
PROVENANCE = """v is mapping and
    v.schema_version | default('') == '1.0' and
    v.node_id | default('') == 'node01' and
    v.simulated is defined and v.simulated is sameas false"""


def compact(text):
    """Normalize whitespace only; never evaluate a Jinja expression."""
    return " ".join(text.split())


def channel_guard(channel):
    extra = " and 0 <= v.light <= 1" if channel == "light" else ""
    return f"""{PROVENANCE} and
        v.sensor_status is defined and v.sensor_status is mapping and
        v.sensor_status.{channel} | default('') == 'ok' and
        v.{channel} is defined and v.{channel} is not none and
        v.{channel} is number and v.{channel} is not boolean{extra}"""


class Node01ConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CONFIG.is_file(), f"Missing formal HA config: {CONFIG}")
        self.sensors = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.assertIsInstance(self.sensors, list)
        self.assertEqual(len(self.sensors), 3)
        self.assertTrue(all(isinstance(item, dict) for item in self.sensors))

    def test_three_entities_bound_to_channels(self):
        base_keys = {
            "name", "unique_id", "state_topic", "value_template",
            "expire_after", "qos", "availability_mode",
            "availability", "json_attributes_topic", "json_attributes_template",
        }
        for sensor, (channel, unit) in zip(self.sensors, CHANNELS.items()):
            with self.subTest(channel=channel):
                expected_keys = (
                    base_keys if unit is None
                    else base_keys | {"unit_of_measurement", "device_class"}
                )
                self.assertEqual(set(sensor), expected_keys)
                self.assertEqual(sensor["name"], f"XiaoXi Node01 {channel.title()}")
                self.assertEqual(sensor["unique_id"], f"xiaoxi_node01_{channel}")
                # Expected initial entity_id only; HA registry must confirm it.
                slug = sensor["name"].lower().replace(" ", "_")
                self.assertEqual(f"sensor.{slug}", f"sensor.xiaoxi_node01_{channel}")
                if unit is not None:
                    self.assertEqual(sensor["unit_of_measurement"], unit)
                    self.assertEqual(sensor["device_class"], channel)
                # Raw state history is kept; long-term statistics are disabled.
                self.assertNotIn("state_class", sensor)
                self.assertEqual(sensor["expire_after"], 35)
                self.assertIs(type(sensor["expire_after"]), int)
                self.assertEqual(sensor["qos"], 0)

    def test_only_exact_derived_topics_and_no_discovery(self):
        for sensor in self.sensors:
            self.assertEqual(sensor["state_topic"], TELEMETRY)
            self.assertEqual(sensor["json_attributes_topic"], TELEMETRY)
            topics = [item["topic"] for item in sensor["availability"]]
            self.assertEqual(topics, [STATUS, TELEMETRY])
            self.assertEqual(len(topics), len(set(topics)))
        text = CONFIG.read_text(encoding="utf-8")
        for forbidden in ("xiaoxi/dorm/", "node90", "discovery", "command"):
            self.assertNotIn(forbidden, text)

    def test_two_distinct_availability_inputs_all_and_strict_status(self):
        status_template = """{% set v = value_json | default({}) %}
            {{ v.state if v is mapping and v | length == 3 and
            v.schema_version | default('') == '1.0' and
            v.node_id | default('') == 'node01' and
            v.state | default('') in ['online', 'offline'] else 'offline' }}"""
        for sensor in self.sensors:
            self.assertEqual(sensor["availability_mode"], "all")
            self.assertEqual(len(sensor["availability"]), 2)
            for item in sensor["availability"]:
                self.assertEqual(set(item), {
                    "topic", "value_template", "payload_available",
                    "payload_not_available",
                })
                self.assertEqual(item["payload_available"], "online")
                self.assertEqual(item["payload_not_available"], "offline")
            self.assertEqual(
                compact(sensor["availability"][0]["value_template"]),
                compact(status_template),
            )

    def test_channel_availability_and_value_share_fail_closed_guard(self):
        for sensor, channel in zip(self.sensors, CHANNELS):
            guard = channel_guard(channel)
            prefix = "{% set v = value_json | default({}) %}"
            availability = f"{prefix} {{{{ 'online' if {guard} else 'offline' }}}}"
            value = f"{prefix} {{{{ v.{channel} if {guard} else 'None' }}}}"
            self.assertEqual(
                compact(sensor["availability"][1]["value_template"]),
                compact(availability),
            )
            self.assertEqual(compact(sensor["value_template"]), compact(value))
            # Textual rejection clauses, not fixture rendering or an interpreter.
            rejection_clauses = {
                "missing value": f"v.{channel} is defined",
                "null value": f"v.{channel} is not none",
                "string value": f"v.{channel} is number",
                "boolean value": f"v.{channel} is not boolean",
                "error/missing status": f"v.sensor_status.{channel} | default('') == 'ok'",
                "missing sensor_status": "v.sensor_status is defined",
                "simulated true/missing": "v.simulated is defined and v.simulated is sameas false",
            }
            for case, clause in rejection_clauses.items():
                with self.subTest(channel=channel, rejection=case):
                    self.assertIn(clause, compact(sensor["value_template"]))
                    self.assertIn(clause, compact(availability))

    def test_attributes_use_message_metadata_and_receive_utc_time(self):
        expected = f"""{{% set v = value_json | default({{}}) %}}
            {{% set valid = {PROVENANCE} and
            v.boot_id is defined and v.boot_id is string and
            v.sequence is defined and v.sequence is integer and
            v.sequence is not boolean %}}
            {{% if valid %}}
            {{{{ {{'boot_id': v.boot_id, 'sequence': v.sequence,
            'simulated': v.simulated, 'received_at': utcnow().isoformat()}}
            | to_json }}}}
            {{% else %}}{{{{ {{}} | to_json }}}}{{% endif %}}"""
        for sensor in self.sensors:
            template = sensor["json_attributes_template"]
            self.assertEqual(compact(template), compact(expected))
            # No channel/value comparison gates metadata on unchanged readings.
            for forbidden in (
                "last_changed", "timestamp", "states(", "this.",
                "temperature", "humidity", "light", "now().timestamp",
            ):
                self.assertNotIn(forbidden, template)
        text = CONFIG.read_text(encoding="utf-8")
        self.assertEqual(text.count("utcnow()"), 3)
        for forbidden in ("scan_interval", "time_pattern", "trigger:"):
            self.assertNotIn(forbidden, text)


class LegacyNode90Tests(unittest.TestCase):
    def test_public_node90_bytes_and_bindings_unchanged(self):
        raw = LEGACY.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), LEGACY_SHA256)
        sensors = yaml.safe_load(raw)["sensor"]
        self.assertEqual(len(sensors), 3)
        self.assertEqual(
            [sensor["unique_id"] for sensor in sensors],
            [f"xiaoxi_node90_{channel}" for channel in ("temperature", "humidity", "light")],
        )
        for sensor in sensors:
            self.assertEqual(sensor["state_topic"], "xiaoxi/dorm/node90/telemetry")
            self.assertEqual(sensor["availability_topic"], "xiaoxi/dorm/node90/status")
            self.assertEqual(sensor["expire_after"], 35)


if __name__ == "__main__":
    unittest.main()
