"""Offline regressions: execute reconstructed production functions with stub SDK/delivery.

No Hermes imports, real config/env reads, network, model or audio playback. AST
loading keeps the actual function bodies while omitting service registration.
"""
import ast
import asyncio
import base64
import concurrent.futures
import contextlib
import inspect
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import typing
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "sources"


def load_functions(relative, names, namespace):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            declared = {node.name}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared = {node.target.id}
        else:
            declared = {target.id for target in getattr(node, "targets", []) if isinstance(target, ast.Name)}
        if declared & set(names):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.decorator_list = []
            selected.append(node)
    module = ModuleType(relative.replace("/", "."))
    module.__dict__.update({key: value for key, value in vars(typing).items() if not key.startswith("__")})
    module.__dict__.update(namespace)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(ROOT / relative), "exec"), module.__dict__)
    return module


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


@contextlib.contextmanager
def http_failure(_message, status, detail):
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status, detail) from exc


class VoicePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = {"XIAOXI_EDGE_VOICE_OVERRIDE": "unrelated-process-value"}
        fake_os = SimpleNamespace(path=os.path, unlink=os.unlink, environ=self.env)
        common = dict(asyncio=asyncio, json=json, os=fake_os, re=re, Path=Path,
                      logger=logging.getLogger("offline-tts-test"))
        self.providers = load_functions("tools/tts_tool_providers.py", (
            "DEFAULT_EDGE_VOICE", "EDGE_BROWSER_VOICES", "_generate_edge_tts",
        ), common)
        self.config = {"provider": "edge", "edge": {"voice": "zh-CN-XiaoxiaoNeural", "speed": 1.1}}
        self.sdk_calls = []
        self.provider_gate = None
        test = self

        class Communicate:
            def __init__(self, text, **kwargs):
                test.sdk_calls.append((text, kwargs))
                self.voice = kwargs["voice"]

            async def save(self, output):
                Path(output).write_bytes(b"stub-not-audio:" + self.voice.encode())

        sdk = SimpleNamespace(Communicate=Communicate)
        tool_error = lambda message, **kw: json.dumps({"success": False, "error": message})
        self.tool = load_functions("tools/tts_tool.py", (
            "DEFAULT_PROVIDER", "_BUILTIN_DISPATCH", "_get_provider", "_error_json", "_run_edge_tts",
            "_select_builtin_engine", "_synthesize_builtin", "_tool_failure",
            "_text_to_speech_single", "_synthesize_chunks", "_ChunkFailed",
            "_apply_call_overrides", "_media_tag", "text_to_speech_tool",
        ), {**common, "tool_error": tool_error, "NOUS_MANAGED_PROVIDER": "nous",
            "EDGE_BROWSER_VOICES": getattr(self.providers, "EDGE_BROWSER_VOICES", frozenset()),
            "DEFAULT_EDGE_VOICE": self.providers.DEFAULT_EDGE_VOICE,
            "BUILTIN_TTS_PROVIDERS": {"edge", "openai", "neutts"},
            "_load_tts_config": lambda: self.config,
            "_resolve_command_provider_config": lambda *args: None,
            "_resolve_max_text_length": lambda *args: 4000,
            "_split_text_for_tts": lambda text, cap: [text],
            "_session_platform": lambda: ("web", False),
            "_resolve_audio_delivery_profile": lambda *args: SimpleNamespace(platform="web", max_file_bytes=10000, target_file_bytes=9000),
            "_resolve_output_base": self.output_base,
            "_build_audio_delivery_files": lambda paths, *args, **kw: (paths, False),
            "_repair_ogg_container": lambda path: path,
            "_finalize_voice_delivery": lambda path, *args: (path, False),
            "_remove_quietly": lambda path: Path(path).unlink(missing_ok=True),
            "_dispatch_to_plugin_provider": lambda *args: None,
            "_importable": lambda importer: self.importable(importer),
            "_import_edge_tts": lambda: sdk,
            "_check_neutts_available": lambda: False,
            "_import_openai_client": lambda: object,
            "_generate_openai_tts": lambda text, output, config, instructions=None: Path(output).write_bytes(b"stub-not-audio:openai"),
            "_generate_edge_tts": self.providers._generate_edge_tts,
        })
        self.providers._origin = lambda: self.tool
        original_run = self.tool._run_edge_tts

        def run_edge(*args):
            if self.provider_gate:
                self.provider_gate.wait(timeout=3)
            original_run(*args)

        self.tool._run_edge_tts = run_edge
        self.audio = load_functions("hermes_cli/web_routers/audio.py", (
            "_SPEAK_MIME_BY_EXT", "_unlink_quietly", "_run_config_scoped", "speak_text",
        ), {**common, "TTSSpeakRequest": SimpleNamespace, "HTTPException": HTTPException,
            "http_failure": http_failure, "base64": base64,
            "_config_profile_scope": lambda profile: contextlib.nullcontext()})
        self.modules = patch.dict(sys.modules, {"tools.tts_tool": self.tool})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    @staticmethod
    def importable(importer):
        try:
            importer()
            return True
        except ImportError:
            return False

    def output_base(self, output, *args):
        if output:
            return Path(output), None
        handle, path = tempfile.mkstemp(dir=self.temp.name, suffix=".mp3")
        os.close(handle)
        return Path(path), None

    def speak(self, voice=None, text="hello"):
        return asyncio.run(self.audio.speak_text(SimpleNamespace(text=text), voice=voice))

    def test_concurrent_requests_keep_voice_and_cached_config_isolated(self):
        self.provider_gate = threading.Barrier(3)
        before = json.loads(json.dumps(self.config))
        selections = ("zh-CN-YunxiNeural", "zh-TW-HsiaoChenNeural", None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(self.speak, selections))
        for voice, result in zip((selection or self.config["edge"]["voice"] for selection in selections), results):
            self.assertEqual(result["provider"], "edge")
            self.assertEqual(result.get("voice"), voice)
            self.assertEqual(base64.b64decode(result["data_url"].split(",")[1]), b"stub-not-audio:" + voice.encode())
        self.assertEqual(self.config, before)
        self.assertEqual(self.env, {"XIAOXI_EDGE_VOICE_OVERRIDE": "unrelated-process-value"})
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_selected_edge_voice_overrides_global_provider(self):
        self.config["provider"] = "openai"
        result = self.speak("zh-CN-YunxiNeural")
        self.assertTrue(result["ok"])
        self.assertEqual((result["provider"], result.get("voice")), ("edge", "zh-CN-YunxiNeural"))
        self.assertEqual(self.config["provider"], "openai")

    def test_omitted_voice_keeps_configured_and_legacy_default(self):
        result = self.speak()
        self.assertEqual(result.get("voice"), "zh-CN-XiaoxiaoNeural")
        self.config = {}
        result = self.speak()
        self.assertEqual(result.get("voice"), "en-US-AriaNeural")

    def test_invalid_voice_is_rejected_before_sdk(self):
        for voice in ("", "browser-native", "zh-CN-MadeUpNeural", "../voice"):
            with self.subTest(voice=voice):
                with self.assertRaises(HTTPException) as error:
                    self.speak(voice)
                self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.sdk_calls, [])

    def test_explicit_edge_cannot_fallback_to_another_provider(self):
        def missing_sdk():
            raise ImportError("stub SDK unavailable")
        self.tool._import_edge_tts = missing_sdk
        fallback_calls = []
        self.tool._check_neutts_available = lambda: fallback_calls.append("neutts") or True
        with self.assertRaises(HTTPException) as error:
            self.speak("zh-CN-YunxiNeural")
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("Edge", error.exception.detail)
        self.assertEqual(fallback_calls, [])

    def test_synthesis_failure_is_an_error_without_success_metadata(self):
        async def failed(*args):
            raise ValueError("stub synthesis failed")
        self.tool._generate_edge_tts = failed
        with self.assertRaises(HTTPException) as error:
            self.speak("zh-CN-YunxiNeural")
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("stub synthesis failed", error.exception.detail)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_omitted_voice_preserves_non_edge_provider_and_old_positional_args(self):
        self.config["provider"] = "openai"
        response = self.speak()
        self.assertEqual(response["provider"], "openai")
        self.assertIsNone(response["voice"])
        result = json.loads(self.tool.text_to_speech_tool("hello", None, 1.0, "read calmly", "openai"))
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(self.sdk_calls, [])

    def test_mismatched_success_metadata_is_rejected_and_file_removed(self):
        for provider, voice in (("neutts", "zh-CN-YunxiNeural"), ("edge", "zh-CN-XiaoxiaoNeural")):
            output, _ = self.output_base(None)
            output.write_bytes(b"stub-not-audio")
            self.tool.text_to_speech_tool = lambda *args, **kwargs: json.dumps({
                "success": True, "provider": provider, "voice": voice, "file_path": str(output),
            })
            with self.assertRaises(HTTPException) as error:
                self.speak("zh-CN-YunxiNeural")
            self.assertEqual(error.exception.status_code, 502)
            self.assertFalse(output.exists())

    def test_unknown_legacy_provider_reports_actual_edge_engine(self):
        self.config["provider"] = "unknown-legacy-provider"
        result = self.speak()
        self.assertEqual(result["provider"], "edge")
        self.assertEqual(result.get("voice"), "zh-CN-XiaoxiaoNeural")

    def test_legacy_tool_and_generator_signatures_still_bind(self):
        inspect.signature(self.tool.text_to_speech_tool).bind("hello", None, 1.0, None, "edge")
        inspect.signature(self.providers._generate_edge_tts).bind("hello", "/unused.mp3", {})
        result = json.loads(self.tool.text_to_speech_tool("hello", None, 1.0, None, "edge"))
        self.assertTrue(result["success"])
        self.assertEqual(result.get("voice"), "zh-CN-XiaoxiaoNeural")

    def test_invalid_tool_result_is_http_500(self):
        for value in ("not-json", "[]", None):
            self.tool.text_to_speech_tool = lambda *args, **kwargs: value
            with self.subTest(value=value):
                with self.assertRaises(HTTPException) as error:
                    self.speak()
                self.assertEqual(error.exception.status_code, 500)

    def test_frontend_cloud_options_match_backend_allowlist(self):
        source = (ROOT / "web/src/components/ChatSidebar.tsx").read_text(encoding="utf-8")
        options = set(re.findall(r'<option value="([^"]+)"', source)) - {"browser-native"}
        self.assertEqual(options, self.tool.EDGE_BROWSER_VOICES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
