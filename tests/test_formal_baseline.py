"""Integration tests for the 7-service security Compose baseline."""
from pathlib import Path
import json
import unittest

import yaml

from scripts.check_repository import HomeAssistantLoader

ROOT = Path(__file__).resolve().parents[1]


class FormalBaselineTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / "deploy/compose.secure.yaml").read_text())
        self.services = self.compose["services"]

    def test_agent_has_only_internal_network_and_query_credential(self):
        self.assertEqual(set(self.services), {
            "mosquitto", "home-assistant", "node01-validator", "read-gateway",
            "hermes", "inference-egress", "dashboard-ingress",
        })
        agent = self.services["hermes"]
        self.assertEqual(agent["networks"], ["agent"])
        self.assertTrue(self.compose["networks"]["agent"]["internal"])
        self.assertNotIn("ports", agent)
        self.assertIn("hermes-data:/opt/data", agent["volumes"])
        model_mount = agent["volumes"][1]
        self.assertEqual(model_mount["source"], "./runtime/secure/whisper-base")
        self.assertEqual(model_mount["target"], "/opt/data/whisper-base")
        self.assertTrue(model_mount["read_only"])
        self.assertFalse(model_mount["bind"]["create_host_path"])
        self.assertEqual(len(agent["volumes"]), 2)
        env = agent["environment"]
        self.assertEqual(env["HASS_URL"], "http://read-gateway:8080")
        self.assertNotIn("HASS_BACKEND_TOKEN", env)
        self.assertEqual(env["HTTPS_PROXY"], "http://inference-egress:3128")
        self.assertTrue({"NET_RAW", "NET_ADMIN"} <= set(agent["cap_drop"]))
        self.assertEqual(set(self.services["read-gateway"]["networks"]), {"backend", "agent"})
        self.assertEqual(set(self.services["inference-egress"]["networks"]), {"agent", "egress-outbound"})
        self.assertEqual(set(self.services["dashboard-ingress"]["networks"]), {"agent", "dashboard-ingress"})

    def test_helpers_keep_source_in_image_and_durable_replay_state(self):
        for name in ("node01-validator", "read-gateway", "inference-egress", "dashboard-ingress"):
            with self.subTest(service=name):
                service = self.services[name]
                self.assertEqual(service["user"], "10001:10001")
                self.assertTrue(service["read_only"])
                self.assertEqual(service["cap_drop"], ["ALL"])
                self.assertFalse(service.get("privileged", False))
                for mount in service.get("volumes", []):
                    if isinstance(mount, dict):
                        self.assertTrue(mount["read_only"])
                        self.assertFalse(mount["bind"]["create_host_path"])
                        self.assertTrue(mount["source"].startswith("./runtime/secure/"))
        self.assertIn("validator-state:/var/lib/xiaoxi", self.services["node01-validator"]["volumes"])
        self.assertNotIn("experiments-private", (ROOT / "deploy/compose.secure.yaml").read_text())

    def test_ha_include_is_parsed_without_opening_runtime_files(self):
        template = (ROOT / "home-assistant/configuration.secure.example.yaml").read_text()
        parsed = yaml.load(template, Loader=HomeAssistantLoader)
        self.assertEqual(parsed["mqtt"]["sensor"], "mqtt/real")
        with self.assertRaises(yaml.constructor.ConstructorError):
            yaml.load("key: !secret never-open-this", Loader=HomeAssistantLoader)

    def test_gateway_template_matches_exact_five_static_real_entities(self):
        expected = set()
        for name in ("node01.yaml", "events.yaml"):
            for sensor in yaml.safe_load((ROOT / "home-assistant/mqtt/real" / name).read_text()):
                expected.add("sensor." + sensor["unique_id"])
        gateway = json.loads((ROOT / "deploy/examples/gateway.example.json").read_text())
        self.assertEqual(set(gateway["allowed_entities"]), expected)
        self.assertEqual(len(expected), 5)
        self.assertNotEqual(gateway["query_token"], gateway["backend_token"])
        self.assertEqual(gateway["backend_url"], "http://home-assistant:8123")

    def test_default_acl_has_no_command_publisher(self):
        user = None
        grants = {}
        for raw in (ROOT / "deploy/examples/mosquitto-acl.conf").read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line.startswith("user "):
                user = line.split()[1]
                grants[user] = []
            elif line.startswith("topic "):
                permission, topic = line.split()[1:]
                grants[user].append((permission, topic))
                if permission in {"write", "readwrite"}:
                    self.assertNotIn("command", topic)
        self.assertTrue(grants["xiaoxi_ha_read"])
        self.assertTrue(all(permission == "read" for permission, _ in grants["xiaoxi_ha_read"]))
        self.assertIn(("read", "xiaoxi/dorm/node02/command"), grants["xiaoxi_node02"])


if __name__ == "__main__":
    unittest.main()
