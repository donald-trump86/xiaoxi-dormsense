"""Exercise the patched segment joiner without importing Whisper or any model."""
import logging
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from test_voice_patch import load_functions


class TranscriptionNormalizationTests(unittest.TestCase):
    def setUp(self):
        module = load_functions("tools/transcription_local.py", ("_join_confident_segments",), {
            "logger": logging.getLogger("offline-stt-test"),
            "_confidence_thresholds": lambda config: (0.6, -1.0),
            "_is_hallucinated_segment": lambda *args: False,
        })
        self.join = module._join_confident_segments
        self.original = "臺灣旅館在小溪旁，是内侧入口；焦大小溪和交大小溪都是原话。"
        self.segments = [SimpleNamespace(text=self.original)]

    def test_script_conversion_preserves_literal_names_and_user_meaning(self):
        calls = []

        def convert(text, locale):
            calls.append((text, locale))
            return text.replace("臺灣", "台湾").replace("旅館", "旅馆")

        with patch.dict(sys.modules, {"zhconv": SimpleNamespace(convert=convert)}):
            result = self.join(self.segments, {})
        self.assertEqual(calls, [(self.original, "zh-cn")])
        self.assertEqual(result, "台湾旅馆在小溪旁，是内侧入口；焦大小溪和交大小溪都是原话。")

    def test_unavailable_normalizer_preserves_original_transcript(self):
        with patch.dict(sys.modules, {"zhconv": None}):
            self.assertEqual(self.join(self.segments, {}), self.original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
