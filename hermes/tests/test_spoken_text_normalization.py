"""Run the patched shared speech cleaner with no provider, network, or audio."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "sources"


class SpokenTextNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "xiaoxi_spoken_normalizer", ROOT / "tools/tts_text_normalize.py"
        )
        cls.normalizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.normalizer)

    def spoken(self, text):
        return self.normalizer.prepare_spoken_text(text, max_chars=None)

    def test_chinese_weather_preserves_all_decimal_and_signed_values(self):
        text = "室内湿度51.5%，温度23.9°C；室外湿度65％，体感−5.2℃，高温+30.5 °C，华氏−4.5 °F。"
        self.assertEqual(
            self.spoken(text),
            "室内湿度百分之51.5，温度23.9摄氏度；室外湿度百分之65，体感负5.2摄氏度，高温正30.5摄氏度，华氏负4.5华氏度。",
        )

    def test_signed_and_leading_decimal_percentages(self):
        self.assertEqual(
            self.spoken("变化-5.25%或+0.5％，误差−.75%。"),
            "变化百分之负5.25或百分之正0.5，误差百分之负.75。",
        )

    def test_ranges_with_shared_or_repeated_units(self):
        cases = (
            ("温度-5–-1°C", "温度负5摄氏度至负1摄氏度"),
            ("温度−4.5℃～+2℃", "温度负4.5摄氏度至正2摄氏度"),
            ("湿度40-60％", "湿度百分之40至百分之60"),
            ("湿度45%—51.5%", "湿度百分之45至百分之51.5"),
            ("华氏10 to 20°F", "华氏10华氏度至20华氏度"),
            ("范围-5--1℉", "范围负5华氏度至负1华氏度"),
            ("湿度−5%-−1%", "湿度百分之负5至百分之负1"),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.spoken(text), expected)

    def test_mixed_chinese_reply_uses_chinese_units(self):
        self.assertEqual(
            self.spoken("天气：humidity 51.5%, temperature -2.3°C; feels like 28°F。"),
            "天气：humidity 百分之51.5, temperature 负2.3摄氏度; feels like 28华氏度。",
        )

    def test_pure_english_preserves_existing_shared_behavior(self):
        self.assertEqual(
            self.spoken("Humidity 51.5%, temperature -2.3°C, range 11–17°F, wind 12km/h."),
            "Humidity 51.5 percent, temperature -2.3 degrees Celsius, range 11 to 17 degrees Fahrenheit, wind 12 kilometres per hour.",
        )

    def test_language_detection_ignores_omitted_code_and_link_targets(self):
        text = "Humidity 51.5%. [Weather](https://example.invalid/天气)\n```\n温度−2℃\n```"
        self.assertEqual(self.spoken(text), "Humidity 51.5 percent. Weather")

    def test_links_keep_labels_and_encoded_urls_are_never_percentages(self):
        text = "查看[天气51.5%](https://example.invalid/a%20b?q=23%C2%B0C) 和 https://example.invalid/65%20percent 温度23.9°C。"
        self.assertEqual(self.spoken(text), "查看天气百分之51.5 和 温度23.9摄氏度。")

    def test_fenced_code_is_omitted_before_conversion(self):
        self.assertEqual(
            self.spoken("湿度51.5%。\n```python\nx = '99% -99°C'\n```\n温度23.9°C。"),
            "湿度百分之51.5。. 温度23.9摄氏度。.",
        )

    def test_chinese_text_is_idempotent_including_cloud_reentry(self):
        for text in (
            "湿度百分之51.5，温度23.9摄氏度，体感负5.2摄氏度。",
            "湿度51.5%，温度−5.2°C，范围-5℃到+2℃。",
        ):
            with self.subTest(text=text):
                once = self.spoken(text)
                self.assertEqual(self.spoken(once), once)

    def test_only_unambiguous_weather_units_are_translated(self):
        self.assertEqual(
            self.spoken("风速12.5km/h，降水2mm，积雪3cm，能见度500m；频率5MHz，速度3m/s，功率8MW，重量7mg。"),
            "风速12.5公里每小时，降水2毫米，积雪3厘米，能见度500米；频率5MHz，速度3m/s，功率8MW，重量7mg。",
        )

    def test_server_caller_passes_complete_normalized_text_to_chunker(self):
        tree = ast.parse((ROOT / "tools/tts_tool.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "text_to_speech_tool")
        future = ast.parse("from __future__ import annotations").body[0]
        received = []

        def split(text, limit):
            received.append((text, limit))
            return []  # Stop at the provider boundary, before any synthesis or file writes.

        namespace = {
            "tool_error": lambda message, **kwargs: message,
            "_load_tts_config": lambda: {},
            "_apply_call_overrides": lambda config, speed, provider: (config, "edge"),
            "_resolve_command_provider_config": lambda *args: None,
            "_resolve_max_text_length": lambda *args: 100,
            "_split_text_for_tts": split,
        }
        exec(compile(ast.Module(body=[future, function], type_ignores=[]), "tts_tool.py", "exec"), namespace)
        tools = ModuleType("tools")
        tools.__path__ = []
        original = "室内51.5%，温度23.9°C，室外65％，体感−5.2℃，华氏32°F。"
        with patch.dict(sys.modules, {"tools": tools, "tools.tts_text_normalize": self.normalizer}):
            namespace["text_to_speech_tool"](original)
        self.assertEqual(received, [(self.spoken(original), 100)])
        self.assertEqual(received[0][0], "室内百分之51.5，温度23.9摄氏度，室外百分之65，体感负5.2摄氏度，华氏32华氏度。")


if __name__ == "__main__":
    unittest.main(verbosity=2)
