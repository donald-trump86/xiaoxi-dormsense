"""Offline contracts for scoped HA retention; not actual purge execution."""
from pathlib import Path
import unittest

import yaml

from scripts.check_repository import HomeAssistantLoader

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = {f"sensor.xiaoxi_node01_{name}" for name in ("temperature", "humidity", "light")}


class EnvironmentRetentionTests(unittest.TestCase):
    def test_native_schedule_deletes_only_three_entities(self):
        items = yaml.safe_load((ROOT / "home-assistant/automations/environment-retention.yaml").read_text())
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "xiaoxi_environment_24h_retention")
        self.assertEqual(item["mode"], "single")
        self.assertIs(item["initial_state"], True)
        self.assertCountEqual(item["triggers"], [
            {"trigger": "time_pattern", "minutes": "/5", "seconds": 0},
            {"trigger": "home" + "assistant", "event": "start"},
        ])
        self.assertEqual(item["actions"], [{
            "action": "recorder.purge_entities",
            "data": {"entity_id": sorted(ENTITIES), "keep_days": 1},
        }])
        self.assertNotIn("conditions", item)

    def test_config_merges_automation_without_global_purge_override(self):
        config = yaml.load((ROOT / "home-assistant/configuration.secure.example.yaml").read_text(),
                           Loader=HomeAssistantLoader)
        self.assertEqual(config["automation"], "automations/environment-retention.yaml")
        self.assertNotIn("recorder", config)
        compose = yaml.safe_load((ROOT / "deploy/compose.secure.yaml").read_text())
        mounts = compose["services"]["home-assistant"]["volumes"]
        target = next(item for item in mounts if isinstance(item, dict)
                      and item["target"] == "/config/automations")
        self.assertEqual(target["source"], "../home-assistant/automations")
        self.assertTrue(target["read_only"])
        self.assertFalse(target["bind"]["create_host_path"])

    def test_environment_stops_long_term_statistics_without_losing_samples(self):
        sensors = yaml.safe_load((ROOT / "home-assistant/mqtt/real/node01.yaml").read_text())
        self.assertEqual({"sensor." + item["unique_id"] for item in sensors}, ENTITIES)
        for item in sensors:
            self.assertNotIn("state_class", item)
            self.assertEqual(item["expire_after"], 35)
            self.assertEqual(item["state_topic"], "xiaoxi/validated/node01/telemetry")
            self.assertIn("received_at", item["json_attributes_template"])
        legacy = yaml.safe_load((ROOT / "home-assistant/mqtt/sensors.yaml").read_text())["sensor"]
        self.assertTrue(all(item["state_class"] == "measurement" for item in legacy))


if __name__ == "__main__":
    unittest.main()
