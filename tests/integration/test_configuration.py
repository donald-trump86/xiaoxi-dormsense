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

    def test_compose_publishes_no_unguarded_listener(self):
        """Mosquitto and Home Assistant must stay loopback-only.

        The Hermes dashboard is the single deliberate exception: OrbStack does
        not forward published container ports on host loopback, so a 127.0.0.1
        bind is unreachable from the host browser. That exception is only
        acceptable while it carries a dashboard password supplied through .env,
        so this test fails closed if the guard is ever dropped.
        """
        config = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
        services = config["services"]
        for name, service in services.items():
            for port in service.get("ports", []):
                if port.startswith("127.0.0.1:"):
                    continue
                self.assertEqual(
                    name, "hermes", f"{name} publishes a non-loopback port: {port}"
                )
                env = dict(
                    item.split("=", 1) for item in service.get("environment", []) if "=" in item
                )
                password = env.get("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", "")
                self.assertTrue(
                    password.startswith("${") and password.endswith("}"),
                    "non-loopback dashboard must take its password from .env, not a literal",
                )
                self.assertIn("HERMES_DASHBOARD_BASIC_AUTH_USERNAME", env)
        self.assertEqual(services["home-assistant"]["profiles"], ["platform"])

    def test_hermes_state_uses_a_named_volume(self):
        """HERMES_HOME holds SQLite databases; a host bind mount corrupts their WAL."""
        config = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
        volumes = config["services"]["hermes"]["volumes"]
        self.assertIn("hermes-data:/opt/data", volumes)
        self.assertIn("hermes-data", config["volumes"])
        for mount in volumes:
            self.assertFalse(
                mount.startswith("./") or mount.startswith("/"),
                f"hermes state must not be a host bind mount: {mount}",
            )

    def test_broker_refuses_anonymous_connections(self):
        config = (ROOT / "deploy/mosquitto/mosquitto.conf").read_text()
        self.assertIn("allow_anonymous false", config)
        self.assertIn("password_file /mosquitto/config/passwords", config)


if __name__ == "__main__":
    unittest.main()
