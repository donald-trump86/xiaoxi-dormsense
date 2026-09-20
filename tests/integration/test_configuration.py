"""Static cross-module assumptions only; does NOT connect to HA or MQTT."""

import unittest

import yaml

from scripts.check_repository import ROOT, HomeAssistantLoader


class ConfigurationTests(unittest.TestCase):
    def test_ha_uses_synthetic_node_and_expiry(self):
        config = yaml.safe_load((ROOT / "home-assistant/mqtt/sensors.yaml").read_text())
        self.assertEqual(len(config["sensor"]), 3)
        for sensor in config["sensor"]:
            self.assertEqual(sensor["state_topic"], "xiaoxi/dorm/node90/telemetry")
            self.assertEqual(sensor["availability_topic"], "xiaoxi/dorm/node90/status")
            self.assertEqual(sensor["expire_after"], 35)
            self.assertIn("value_json.state", sensor["availability_template"])
            self.assertIn("is not none", sensor["value_template"])

    def test_ha_include_exists(self):
        path = ROOT / "home-assistant/configuration.example.yaml"
        config = yaml.load(path.read_text(), Loader=HomeAssistantLoader)
        self.assertTrue((path.parent / config["mqtt"]).is_file())

    def test_compose_is_loopback_only(self):
        config = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
        for service in config["services"].values():
            for port in service.get("ports", []):
                self.assertTrue(port.startswith("127.0.0.1:"), port)
        self.assertEqual(config["services"]["home-assistant"]["profiles"], ["platform"])

    def test_broker_refuses_anonymous_connections(self):
        config = (ROOT / "deploy/mosquitto/mosquitto.conf").read_text()
        self.assertIn("allow_anonymous false", config)
        self.assertIn("password_file /mosquitto/config/passwords", config)


if __name__ == "__main__":
    unittest.main()
