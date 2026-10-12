"""Black-box checks for the local HTTP server's security boundary."""

import http.client
import hmac
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch


fake_db = types.ModuleType("db")
fake_db.memory_prompt_block = lambda limit=24: ""
sys.modules.setdefault("db", fake_db)

import app  # noqa: E402


class HttpSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.AgentMVPHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def request_sse(self, path, payload, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            request_headers = {"Content-Type": "application/json"}
            request_headers.update(headers or {})
            connection.request("POST", path, body=json.dumps(payload).encode("utf-8"),
                               headers=request_headers)
            response = connection.getresponse()
            lines = []
            events = []
            for _ in range(20):
                line = response.fp.readline().decode("utf-8").strip()
                lines.append(line)
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    events.append(event)
                    if event.get("type") == "end":
                        break
            return response.status, lines, events
        finally:
            connection.close()

    def test_expected_public_assets_remain_available(self):
        for path in ("/api/health", "/", "/style.css", "/script.js", "/solana-wallet.js",
                     "/pet.html", "/pixi-unsafe-eval.min.js",
                     "/companion-room-night.png"):
            with self.subTest(path=path):
                status, _ = self.request("GET", path)
                self.assertEqual(status, 200)

    def test_api_responses_are_not_cacheable_or_mime_sniffed(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            response.read()
        finally:
            connection.close()

        class HeaderRecorder:
            def __init__(self):
                self.headers = {}

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.headers[name] = value

            def end_headers(self):
                pass

        stream = HeaderRecorder()
        app.AgentMVPHandler._begin_sse(stream)
        self.assertEqual(stream.status, 200)
        self.assertEqual(stream.headers["Cache-Control"], "no-store, no-transform")
        self.assertEqual(stream.headers["X-Content-Type-Options"], "nosniff")

    def test_embedded_html_csp_blocks_cross_port_resources(self):
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}):
            for path in ("/", "/index.html", "/pet.html"):
                with self.subTest(path=path):
                    connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        policy = response.getheader("Content-Security-Policy") or ""
                        self.assertIn("connect-src 'self'", policy)
                        self.assertIn("img-src 'self' data: blob:", policy)
                        self.assertIn("script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'", policy)
                        self.assertNotIn(" 'unsafe-eval'", policy)
                        self.assertNotIn("https:", policy)
                        response.read()
                    finally:
                        connection.close()

    def test_model_config_save_is_atomic_and_rejects_line_injection(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(app.pathlib.Path, "home", return_value=Path(temp_dir)), \
                patch.object(app, "ENV_VARS", app.ENV_VARS.copy()), \
                patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}):
            env_dir = Path(temp_dir) / ".config" / "gmgn"
            env_dir.mkdir(parents=True)
            env_path = env_dir / ".env"
            env_path.write_text("KEEP=old\n", encoding="utf-8")
            self.assertTrue(app.save_env_config({"GEMINI_API_KEY": "demo-key"}))
            expected = env_path.read_text(encoding="utf-8")
            self.assertIn('GEMINI_API_KEY="demo-key"', expected)
            self.assertIn("KEEP=old", expected)
            self.assertFalse(app.save_env_config({
                "GEMINI_API_KEY": "bad\nENABLE_SYSTEM_COMMANDS=true"}))
            self.assertEqual(env_path.read_text(encoding="utf-8"), expected)
            with patch.object(app.os, "replace", side_effect=OSError("disk error")):
                self.assertFalse(app.save_env_config({"GEMINI_API_KEY": "new-key"}))
            self.assertEqual(env_path.read_text(encoding="utf-8"), expected)
            self.assertEqual(list(env_dir.glob(".env-*")), [])
            self.assertTrue(app.save_env_config({"GEMINI_API_KEY": ""}))
            self.assertNotIn("GEMINI_API_KEY", env_path.read_text(encoding="utf-8"))

    def test_user_model_key_survives_config_reload(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(app.pathlib.Path, "home", return_value=Path(temp_dir)), \
                patch.dict(os.environ, {}, clear=True), \
                patch.object(app, "ENV_VARS", {}):
            self.assertTrue(app.save_env_config({
                "GEMINI_API_KEY": "test-only-key", "LLM_BACKEND": "gemini",
            }))
            # A process restart re-reads the app-private .env file.
            app.ENV_VARS = {}
            reloaded = app.load_env()
            self.assertEqual(reloaded["GEMINI_API_KEY"], "test-only-key")
            self.assertEqual(reloaded["LLM_BACKEND"], "gemini")

    def test_model_config_route_reports_write_failure(self):
        with patch.object(app, "save_env_config", return_value=False):
            status, body = self.request(
                "POST", "/api/system/save_gemini_key",
                body=b'{"gemini_key":"demo-key"}',
                headers={"Content-Type": "application/json"})
        self.assertEqual(status, 500)
        self.assertIn(b"Could not save model configuration", body)

    def test_embedded_model_config_exception_hides_private_details(self):
        token = "k" * 43
        private_detail = "private-key-material-must-not-leak"
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app, "save_env_config", side_effect=RuntimeError(private_detail)):
            status, body = self.request(
                "POST", "/api/system/save_gemini_key",
                body=b'{"gemini_key":"demo-key"}',
                headers={"Content-Type": "application/json",
                         "Cookie": "magi_session=" + token})
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body), {"error": "Could not save model configuration"})
        self.assertNotIn(private_detail.encode(), body)

    def test_embedded_model_config_rejects_custom_endpoints_and_bad_types(self):
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", "test-session-token"), \
                patch.object(app, "save_env_config") as save:
            for payload in ({"gemini_key": "demo", "ai_url": "http://127.0.0.1:9999"},
                            {"gemini_key": ["demo"]},
                            {"gemini_key": 'demo\\nvalue'},
                            {"gemini_key": 'demo"value'},
                            {"gemini_key": "x" * 513}):
                with self.subTest(payload=payload):
                    status, _ = self.request(
                        "POST", "/api/system/save_gemini_key",
                        body=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json",
                                 "Cookie": "magi_session=test-session-token"})
                    self.assertEqual(status, 400)
            save.assert_not_called()
            status, _ = self.request(
                "POST", "/api/system/save_gemini_key",
                body=b'{"gemini_key":"demo"}',
                headers={"Content-Type": "application/json",
                         "Cookie": "magi_session=test-session-token"})
            self.assertEqual(status, 200)
            save.assert_called_once_with({"GEMINI_API_KEY": "demo", "LLM_BACKEND": "gemini",
                                         "AI_URL": "", "AI_KEY": "",
                                         "AI_MODEL": app.DEFAULT_GEMINI_MODEL})

    def test_embedded_compatible_model_validates_and_persists_route(self):
        headers = {"Content-Type": "application/json", "Cookie": "magi_session=test-token"}
        good = {"gemini_key": "", "ai_url": "https://models.example/v1/chat/completions",
                "ai_key": "test-only-key", "ai_model": "test-model"}
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", "test-token"), \
                patch.object(app, "save_env_config", return_value=True) as save:
            for changes in ({"ai_url": "http://models.example/v1/chat/completions"},
                            {"ai_url": "https://user:secret@models.example/v1/chat/completions"},
                            {"ai_url": "https://models.example/v1/chat/completions?key=secret"},
                            {"ai_key": "bad\nkey"}, {"ai_model": ""}, {"ai_key": ""},
                            {"gemini_key": "another-key"}):
                status, _ = self.request("POST", "/api/system/save_gemini_key",
                                         body=json.dumps({**good, **changes}).encode(), headers=headers)
                self.assertEqual(status, 400)
            save.assert_not_called()
            status, _ = self.request("POST", "/api/system/save_gemini_key",
                                     body=json.dumps(good).encode(), headers=headers)
            self.assertEqual(status, 200)
            saved = save.call_args.args[0]
            self.assertEqual(saved["LLM_BACKEND"], "openai")
            self.assertEqual(saved["AI_URL"], good["ai_url"])
            self.assertEqual(saved["AI_MODEL"], "test-model")
            self.assertEqual(saved["GEMINI_API_KEY"], "")
            self.assertEqual(saved["GOOGLE_ACCESS_TOKEN"], "")

    def test_embedded_first_run_can_save_user_model_key(self):
        token = "t" * 48
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app.pathlib.Path, "home", return_value=Path(temp_dir)), \
                patch.object(app, "ENV_VARS", app.ENV_VARS.copy()), \
                patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}):
            status, _ = self.request(
                "POST", "/api/system/save_gemini_key",
                body=b'{"gemini_key":"demo-key"}',
                headers={"Content-Type": "application/json",
                         "Cookie": f"magi_session={token}"})
            self.assertEqual(status, 200)
            config = (Path(temp_dir) / ".config" / "gmgn" / ".env").read_text(
                encoding="utf-8")
            self.assertIn('GEMINI_API_KEY="demo-key"', config)
            self.assertIn('LLM_BACKEND="gemini"', config)

    def test_embedded_model_status_reports_key_presence_without_returning_key(self):
        token = "m" * 43
        private_key = "private-gemini-key-must-not-leak"
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app, "load_env", return_value={"GEMINI_API_KEY": private_key}):
            status, body = self.request("GET", "/api/system/google_status",
                                        headers={"Cookie": "magi_session=" + token})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["gemini_key_configured"])
        self.assertEqual(json.loads(body)["gemini_key"], "")
        self.assertNotIn(private_key.encode(), body)

    def test_embedded_chat_rejects_attachments_without_writing_files(self):
        token = "t" * 48
        payload = json.dumps({"message": "describe this", "attachments": [{
            "name": "picture.png", "type": "image/png", "data": "data:image/png;base64,AAAA",
        }]}).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app.pathlib.Path, "home", return_value=Path(temp_dir)):
            for route in ("/api/chat", "/api/chat/stream"):
                with self.subTest(route=route):
                    status, body = self.request(
                        "POST", route, body=payload,
                        headers={"Content-Type": "application/json",
                                 "Cookie": f"magi_session={token}"})
                    self.assertEqual(status, 501)
                    self.assertIn(b"Attachments are not yet supported", body)
            self.assertFalse((Path(temp_dir) / "micro-agi-mvp" / "uploads").exists())

    def test_byok_chat_uses_current_default_gemini_model(self):
        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return io.BytesIO(b'{"candidates":[{"content":{"parts":['
                                  b'{"thought":true,"text":"internal"},'
                                  b'{"text":"ok"}]},"finishReason":"STOP"}]}')

        settings = {"GEMINI_API_KEY": "demo-key"}
        with patch.object(app, "load_env", return_value=settings), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            route = app._llm_route_setup([{"role": "user", "content": "hello"}])
            self.assertEqual(route["mode"], "gemini_stream")
            self.assertIn("/models/gemini-3.8-flash:streamGenerateContent", route["api_url"])
            self.assertNotIn("demo-key", route["api_url"])
            self.assertEqual(route["headers"]["x-goog-api-key"], "demo-key")
            self.assertEqual(app.call_llm([{"role": "user", "content": "hello"}]), "ok")
        self.assertEqual(len(requests), 1)
        self.assertIn("/models/gemini-3.8-flash:generateContent", requests[0].full_url)
        self.assertNotIn("demo-key", requests[0].full_url)
        self.assertEqual(requests[0].get_header("X-goog-api-key"), "demo-key")

    def test_gemini_stream_hides_thought_parts(self):
        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

            def read(self, size=-1):
                raise AssertionError("SSE must be consumed line by line")

        requests = []
        stream = (b'data: {"candidates":[{"content":{"parts":['
                  b'{"thought":true,"text":"internal"}]}}]}\n\n'
                  b'data: {"candidates":[{"content":{"parts":['
                  b'{"text":"visible"}]},"finishReason":"STOP"}]}\n\n')

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeStream(stream)

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            self.assertEqual(list(app.call_llm_stream(
                [{"role": "user", "content": "hello"}])), ["visible"])
        self.assertEqual(len(requests), 1)
        self.assertNotIn("demo-key", requests[0].full_url)
        self.assertEqual(requests[0].get_header("X-goog-api-key"), "demo-key")

    def test_gemini_only_thought_parts_are_not_answer(self):
        self.assertEqual(app.gemini_visible_text({
            "candidates": [{"content": {"parts": [
                {"thought": True, "text": "internal"},
            ]}}]}), "")

    def test_gemini_stream_eof_without_finish_reason_is_incomplete(self):
        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeStream(b'data: {"candidates":[{"content":{"parts":'
                                  b'[{"text":"partial"}]}}]}\n\n')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            chunks = app.call_llm_stream([{"role": "user", "content": "hello"}])
            self.assertEqual(next(chunks), "partial")
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                next(chunks)
        self.assertEqual(len(requests), 1)

    def test_gemini_stream_error_after_partial_text_is_incomplete(self):
        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeStream(b'data: {"candidates":[{"content":{"parts":'
                                  b'[{"text":"partial"}]}}]}\n\n'
                                  b'data: {"error":{"message":"private upstream detail"}}\n\n')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            chunks = app.call_llm_stream([{"role": "user", "content": "hello"}])
            self.assertEqual(next(chunks), "partial")
            with self.assertRaises(RuntimeError) as caught:
                next(chunks)
        self.assertIn("手动重试", str(caught.exception))
        self.assertNotIn("private upstream detail", str(caught.exception))

    def test_gemini_stream_max_tokens_is_not_a_complete_answer(self):
        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeStream(b'data: {"candidates":[{"content":{"parts":'
                                  b'[{"text":"cut off"}]},"finishReason":"MAX_TOKENS"}]}\n\n')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            chunks = app.call_llm_stream([{"role": "user", "content": "hello"}])
            self.assertEqual(next(chunks), "cut off")
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                next(chunks)

    def test_gemini_nonstream_max_tokens_is_not_a_complete_answer(self):
        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return io.BytesIO(b'{"candidates":[{"content":{"parts":'
                                  b'[{"text":"cut off"}]},"finishReason":"MAX_TOKENS"}]}')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "Gemini 请求失败"):
                app.call_llm([{"role": "user", "content": "hello"}])
        self.assertEqual(len(requests), 1)

    def test_gemini_stream_json_fallback_requires_normal_finish(self):
        requests = []

        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "application/json"}

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeStream(b'{"candidates":[{"content":{"parts":'
                                  b'[{"text":"cut off"}]},"finishReason":"MAX_TOKENS"}]}')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                list(app.call_llm_stream([{"role": "user", "content": "hello"}]))
        self.assertEqual(len(requests), 1)

    def test_gemini_oversized_sse_line_does_not_retry(self):
        requests = []

        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeStream(b'data: ' + b'x' * 100 + b'\n\n')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app, "MAX_LLM_RESPONSE_BYTES", 64), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                list(app.call_llm_stream([{"role": "user", "content": "hello"}]))
        self.assertEqual(len(requests), 1)

    def test_gemini_many_small_sse_lines_respect_total_limit(self):
        requests = []

        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeStream(b': keepalive\n' * 10)

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app, "MAX_LLM_RESPONSE_BYTES", 64), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                list(app.call_llm_stream([{"role": "user", "content": "hello"}]))
        self.assertEqual(len(requests), 1)

    def test_gemini_oversized_json_fallback_does_not_retry(self):
        requests = []

        class FakeStream(io.BytesIO):
            headers = {"Content-Type": "application/json"}

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeStream(b'{"candidates":' + b' ' * 100 + b'[]}')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app, "MAX_LLM_RESPONSE_BYTES", 64), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                list(app.call_llm_stream([{"role": "user", "content": "hello"}]))
        self.assertEqual(len(requests), 1)

    def test_gemini_oversized_nonstream_response_does_not_retry(self):
        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return io.BytesIO(b'{"candidates":' + b' ' * 100 + b'[]}')

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app, "MAX_LLM_RESPONSE_BYTES", 64), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "Gemini 请求失败"):
                app.call_llm([{"role": "user", "content": "hello"}])
        self.assertEqual(len(requests), 1)

    def test_gemini_timeout_does_not_repeat_user_billed_request(self):
        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                raise TimeoutError("timed out")

        settings = {"GEMINI_API_KEY": "demo-key", "AI_MODEL": "gemini-3.5-flash-lite"}
        with patch.object(app, "load_env", return_value=settings), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                app.call_llm([{"role": "user", "content": "hello"}])
        self.assertEqual(len(requests), 1)
        for request in requests:
            self.assertIn("/models/gemini-3.5-flash-lite:generateContent", request.full_url)
            self.assertNotIn("demo-key", request.full_url)
            self.assertEqual(request.get_header("X-goog-api-key"), "demo-key")

    def test_interrupted_gemini_stream_does_not_generate_again(self):
        requests = []

        class BrokenStream(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

            def __init__(self):
                super().__init__(b'data: {"candidates":[{"content":{"parts":'
                                 b'[{"text":"partial"}]}}]}\n\n')

            def readline(self, size=-1):
                chunk = super().readline(size)
                if not chunk:
                    raise OSError("connection lost")
                return chunk

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return BrokenStream()

        with patch.object(app, "load_env", return_value={"GEMINI_API_KEY": "demo-key"}), \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            chunks = app.call_llm_stream([{"role": "user", "content": "hello"}])
            self.assertEqual(next(chunks), "partial")
            with self.assertRaisesRegex(RuntimeError, "手动重试"):
                next(chunks)
        self.assertEqual(len(requests), 1)

    def test_gemini_rate_limit_does_not_refresh_other_credentials_or_retry(self):
        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                raise app.urllib.error.HTTPError(request.full_url, 429, "quota", None, None)

        settings = {"GEMINI_API_KEY": "demo-key", "GOOGLE_ACCESS_TOKEN": "old-token",
                    "GOOGLE_REFRESH_TOKEN": "old-refresh"}
        with patch.object(app, "load_env", return_value=settings), \
                patch.object(app, "refresh_google_token") as refresh, \
                patch.object(app.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "额度不足"):
                app.call_llm([{"role": "user", "content": "hello"}])
            refresh.assert_not_called()
        self.assertEqual(len(requests), 1)

    def test_embedded_server_bounds_pre_auth_slow_connections(self):
        class SmallEmbeddedServer(app.EmbeddedHTTPServer):
            MAX_ACTIVE_REQUESTS = 2
            REQUEST_TIMEOUT_SECONDS = 2

        server = SmallEmbeddedServer(("127.0.0.1", 0), app.AgentMVPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        sockets = []
        try:
            for _ in range(2):
                sockets.append(socket.create_connection(server.server_address, timeout=1))
            deadline = time.monotonic() + 2
            while server._request_slots._value != 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(server._request_slots._value, 0)

            # A third peer receives no worker thread, even without sending headers.
            extra = socket.create_connection(server.server_address, timeout=1)
            try:
                extra.settimeout(1)
                self.assertEqual(extra.recv(1), b"")
            finally:
                extra.close()

            sockets[0].close()
            deadline = time.monotonic() + 2
            while server._request_slots._value == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreater(server._request_slots._value, 0)
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=2)
            try:
                connection.request("GET", "/api/health")
                self.assertEqual(connection.getresponse().status, 200)
            finally:
                connection.close()
        finally:
            for sock in sockets:
                sock.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_embedded_server_releases_idle_connection_after_timeout(self):
        class FastTimeoutServer(app.EmbeddedHTTPServer):
            MAX_ACTIVE_REQUESTS = 1
            REQUEST_TIMEOUT_SECONDS = 0.2

        server = FastTimeoutServer(("127.0.0.1", 0), app.AgentMVPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        peer = socket.create_connection(server.server_address, timeout=1)
        try:
            deadline = time.monotonic() + 2
            was_occupied = False
            while time.monotonic() < deadline:
                if server._request_slots._value == 0:
                    was_occupied = True
                if was_occupied and server._request_slots._value == 1:
                    break
                time.sleep(0.01)
            self.assertTrue(was_occupied)
            self.assertEqual(server._request_slots._value, 1)
            peer.settimeout(1)
            self.assertEqual(peer.recv(1), b"")
        finally:
            peer.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_private_files_and_encoded_traversal_are_not_served(self):
        for path in ("/.env", "/micro_agi.db", "/mcp_config.json", "/app.py",
                     "/android_host/README.md", "/Hiyori/%2e%2e/%2eenv"):
            with self.subTest(path=path):
                status, _ = self.request("GET", path)
                self.assertEqual(status, 404)

    def test_head_cannot_probe_private_file_metadata(self):
        for path in ("/.env", "/micro_agi.db", "/mcp_config.json"):
            with self.subTest(path=path):
                status, _ = self.request("HEAD", path)
                self.assertEqual(status, 501)

    def test_extension_catalog_reports_only_detected_local_capabilities(self):
        status, body = self.request("GET", "/api/system/extensions")
        self.assertEqual(status, 200)
        catalog = json.loads(body)
        self.assertTrue(all(item["status"] == "detected" for item in catalog))
        self.assertFalse(any(item["type"] == "mcp" for item in catalog))
        self.assertFalse(any(item["id"] == "github" for item in catalog))
        self.assertNotIn("Authorization", body.decode("utf-8"))

    def test_approve_stream_failure_keeps_one_http_response(self):
        def broken_stream(*args):
            yield {"type": "token", "text": "partial"}
            raise RuntimeError("synthetic failure")

        with patch.object(app, "resume_agent_run_stream", side_effect=broken_stream), patch.object(app.traceback, "print_exc"):
            status, lines, events = self.request_sse(
                "/api/approve/stream", {"approved": False, "chat_id": "test-chat"})
        self.assertEqual(status, 200)
        self.assertEqual([event["type"] for event in events], ["token", "error", "end"])
        self.assertFalse(any(line.startswith("HTTP/") for line in lines))

    def test_chat_stream_failure_keeps_one_http_response(self):
        def broken_stream(*args):
            yield {"type": "token", "text": "partial"}
            raise RuntimeError("synthetic failure")

        fake_ai_os = types.ModuleType("ai_os")
        fake_ai_os.try_extract_memory_from_user_text = lambda text: []
        with patch.object(app.db, "update_chat_time", create=True), patch.object(app.db, "save_message", create=True), patch.dict(sys.modules, {"ai_os": fake_ai_os}), patch.object(app, "start_agent_run_stream", side_effect=broken_stream), patch.object(app.traceback, "print_exc"):
            status, lines, events = self.request_sse(
                "/api/chat/stream", {"message": "hello", "history": [],
                                     "project_id": "test-project", "chat_id": "test-chat"})
        self.assertEqual(status, 200)
        self.assertEqual([event["type"] for event in events], ["meta", "token", "error", "end"])
        self.assertFalse(any(line.startswith("HTTP/") for line in lines))

    def test_chat_stream_error_event_is_not_saved_as_assistant_answer(self):
        def partial_then_error(*args):
            yield {"type": "token", "text": "partial"}
            yield {"type": "error", "error": "generation incomplete"}

        fake_ai_os = types.ModuleType("ai_os")
        fake_ai_os.try_extract_memory_from_user_text = lambda text: []
        with patch.object(app.db, "update_chat_time", create=True), \
                patch.object(app.db, "save_message", create=True) as save_message, \
                patch.dict(sys.modules, {"ai_os": fake_ai_os}), \
                patch.object(app, "start_agent_run_stream", side_effect=partial_then_error):
            status, _, events = self.request_sse(
                "/api/chat/stream", {"message": "hello", "history": [],
                                     "project_id": "test-project", "chat_id": "test-chat"})
        self.assertEqual(status, 200)
        self.assertEqual([event["type"] for event in events],
                         ["meta", "token", "error", "end"])
        self.assertEqual(save_message.call_count, 1)
        self.assertEqual(save_message.call_args.args[1], "user")

    def test_nonstream_chat_error_is_not_saved_as_assistant_answer(self):
        fake_ai_os = types.ModuleType("ai_os")
        fake_ai_os.try_extract_memory_from_user_text = lambda text: []
        with patch.object(app.db, "update_chat_time", create=True), \
                patch.object(app.db, "save_message", create=True) as save_message, \
                patch.dict(sys.modules, {"ai_os": fake_ai_os}), \
                patch.object(app, "start_agent_run", return_value={
                    "status": "error", "error": "模型请求未完成"}):
            status, body = self.request("POST", "/api/chat", body=json.dumps({
                "message": "private message", "history": [], "project_id": "test-project",
                "chat_id": "test-chat"}).encode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "error")
        self.assertEqual(save_message.call_count, 1)
        self.assertEqual(save_message.call_args.args[1], "user")

    def test_embedded_chat_exception_does_not_expose_private_details(self):
        token = "p" * 43
        private_detail = "private-upstream-token-should-not-leak"
        fake_ai_os = types.ModuleType("ai_os")
        fake_ai_os.try_extract_memory_from_user_text = lambda text: []
        headers = {"Cookie": "magi_session=" + token}
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app.db, "update_chat_time", create=True), \
                patch.object(app.db, "save_message", create=True), \
                patch.dict(sys.modules, {"ai_os": fake_ai_os}), \
                patch.object(app, "start_agent_run", side_effect=RuntimeError(private_detail)), \
                patch.object(app.traceback, "print_exc") as log_error:
            status, body = self.request("POST", "/api/chat", body=json.dumps({
                "message": "hello", "history": [], "project_id": "test-project",
                "chat_id": "test-chat"}).encode("utf-8"), headers=headers)
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body), {"error": "聊天请求失败，请重试"})
        self.assertNotIn(private_detail.encode(), body)
        log_error.assert_not_called()

    def test_embedded_chat_stream_exception_does_not_expose_private_details(self):
        token = "q" * 43
        private_detail = "private-upstream-token-should-not-leak"
        fake_ai_os = types.ModuleType("ai_os")
        fake_ai_os.try_extract_memory_from_user_text = lambda text: []

        def broken_stream(*args):
            yield {"type": "token", "text": "partial"}
            raise RuntimeError(private_detail)

        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app.db, "update_chat_time", create=True), \
                patch.object(app.db, "save_message", create=True), \
                patch.dict(sys.modules, {"ai_os": fake_ai_os}), \
                patch.object(app, "start_agent_run_stream", side_effect=broken_stream), \
                patch.object(app.traceback, "print_exc") as log_error:
            status, lines, events = self.request_sse(
                "/api/chat/stream", {"message": "hello", "history": [],
                                     "project_id": "test-project", "chat_id": "test-chat"},
                headers={"Cookie": "magi_session=" + token})
        self.assertEqual(status, 200)
        self.assertEqual([event["type"] for event in events],
                         ["meta", "token", "error", "end"])
        self.assertEqual(events[-2]["error"], "聊天请求失败，请重试")
        self.assertNotIn(private_detail, "\n".join(lines))
        log_error.assert_not_called()

    def test_nonlocal_host_and_foreign_origin_are_rejected(self):
        status, _ = self.request("GET", "/api/health", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/system/command", body=b"{}",
                                 headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/system/command", body=b"{}",
                                 headers={"Origin": "http://127.0.0.1:invalid"})
        self.assertEqual(status, 403)

    def test_cross_site_browser_requests_cannot_reach_local_apis(self):
        for site in ("cross-site", "same-site"):
            with self.subTest(site=site):
                status, _ = self.request("GET", "/api/health",
                                         headers={"Sec-Fetch-Site": site})
                self.assertEqual(status, 403)
                status, _ = self.request("POST", "/api/system/command", body=b"{}",
                                         headers={"Sec-Fetch-Site": site})
                self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/health",
                                 headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/health",
                                 headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(status, 200)
        status, _ = self.request("GET", "/api/health",
                                 headers={"Sec-Fetch-Site": "none"})
        self.assertEqual(status, 200)

    def test_solana_balance_rejects_invalid_address_without_rpc(self):
        with patch.object(app.solana_watch, "get_devnet_balance") as lookup:
            status, body = self.request("GET", "/api/solana/devnet/balance?address=not-a-key")
        self.assertEqual(status, 400)
        self.assertIn(b"Invalid Solana public key", body)
        lookup.assert_not_called()

    def test_solana_balance_returns_read_only_devnet_result(self):
        address = "11111111111111111111111111111111"
        expected = {"network": "devnet", "address": address, "lamports": "1000000000", "slot": 42}
        with patch.object(app.solana_watch, "get_devnet_balance", return_value=expected) as lookup:
            status, body = self.request("GET", "/api/solana/devnet/balance?address=" + address)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), expected)
        lookup.assert_called_once_with(address)

    def test_system_command_is_disabled_by_default(self):
        with patch.object(app, "ENV_VARS", {"ENABLE_SYSTEM_COMMANDS": "false"}):
            status, _ = self.request("POST", "/api/system/command",
                                     body=b'{"command":"echo must-not-run"}',
                                     headers={"Content-Type": "application/json"})
        self.assertEqual(status, 403)

    def test_embedded_mode_disables_shell_even_if_legacy_flag_is_on(self):
        token = "a" * 43
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app, "ENV_VARS", {"ENABLE_SYSTEM_COMMANDS": "true"}):
            status, body = self.request("POST", "/api/system/command",
                                        body=b'{"cmd":"echo must-not-run"}',
                                        headers={"Content-Type": "application/json",
                                                 "Cookie": "magi_session=" + token})
            health_status, health_body = self.request("GET", "/api/health")
            self.assertNotIn("<execute>", app.get_system_prompt())
        self.assertEqual(status, 403)
        self.assertIn(b"disabled", body)
        self.assertEqual(health_status, 200)
        self.assertTrue(json.loads(health_body)["embedded"])
        self.assertNotIn(token.encode("ascii"), health_body)
        self.assertEqual(json.loads(health_body)["proof"], hmac.new(
            token.encode("ascii"), b"micro-agi-embedded-health-v1", "sha256").hexdigest())

    def test_embedded_api_requires_private_app_session(self):
        token = "b" * 43
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token):
            missing, _ = self.request("GET", "/api/system/google_status")
            invalid, _ = self.request("GET", "/api/system/google_status",
                                      headers={"Cookie": "magi_session=wrong"})
            valid, _ = self.request("GET", "/api/solana/devnet/balance?address=invalid",
                                    headers={"Cookie": "magi_session=" + token})
            cross_site, _ = self.request("GET", "/api/solana/devnet/balance?address=invalid",
                                         headers={"Cookie": "magi_session=" + token,
                                                  "Sec-Fetch-Site": "cross-site"})
        self.assertEqual((missing, invalid, valid, cross_site), (403, 403, 400, 403))

    def test_embedded_health_reports_missing_ui_assets_as_not_ready(self):
        token = "f" * 43
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app, "embedded_assets_ready", return_value=False):
            status, body = self.request("GET", "/api/health")
        health = json.loads(body)
        self.assertEqual(status, 200)
        self.assertFalse(health["ok"])
        self.assertFalse(health["ready"])
        self.assertTrue(health["embedded"])

    def test_embedded_mode_rejects_unported_termux_routes_before_subprocess(self):
        token = "c" * 43
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app.subprocess, "run") as run:
            headers = {"Cookie": "magi_session=" + token}
            for path in ("/api/hardware/battery", "/api/hardware/clipboard",
                         "/api/system/update", "/api/wechat/status",
                         "/api/aios/digest"):
                with self.subTest(path=path):
                    status, body = self.request("GET", path, headers=headers)
                    self.assertEqual(status, 501)
                    self.assertIn(b"native Android migration", body)
            status, _ = self.request("POST", "/api/system/auth/init", body=b"{}",
                                     headers=headers)
            self.assertEqual(status, 501)
            status, _ = self.request("POST", "/api/system/google_logout", body=b"{}",
                                     headers=headers)
            self.assertEqual(status, 501)
            status, _ = self.request("POST", "/api/aios/entry/refresh", body=b"{}",
                                     headers=headers)
            self.assertEqual(status, 501)
            for path in ("/api/approve", "/api/approve/stream"):
                with self.subTest(path=path):
                    status, body = self.request("POST", path,
                                                body=b'{"approved":true}', headers=headers)
                    self.assertEqual(status, 501)
                    self.assertIn(b"native Android migration", body)
            status, _ = self.request("GET", "/google_login")
            self.assertEqual(status, 501)
            run.assert_not_called()

    def test_rejected_small_post_body_returns_status_without_socket_reset(self):
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", "s" * 43):
            # Closing before consuming a POST body used to intermittently
            # produce WinError 10053 instead of the intended JSON denial.
            for _ in range(12):
                status, body = self.request("POST", "/api/system/auth/init",
                                            body=b"{}", headers={"Cookie": "magi_session=invalid"})
                self.assertEqual(status, 403)
                self.assertIn(b"Invalid app session", body)

    def test_embedded_aios_status_uses_only_local_memory_data(self):
        token = "e" * 43
        fake_ai_os = types.ModuleType("ai_os")
        fake_ai_os.collect_system_snapshot = lambda: self.fail("Termux probe executed")
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app.db, "list_memories", return_value=[], create=True), \
                patch.object(app.db, "list_digests", return_value=[], create=True), \
                patch.object(app.db, "list_recent_chats", return_value=[], create=True), \
                patch.dict(sys.modules, {"ai_os": fake_ai_os}), \
                patch.object(app.subprocess, "run") as run:
            status, body = self.request("GET", "/api/aios/status",
                                        headers={"Cookie": "magi_session=" + token})
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["snapshot"]["memories"], 0)
            self.assertFalse(data["notification"]["available"])
            run.assert_not_called()

    def test_embedded_mode_never_runs_legacy_agy_cli(self):
        token = "d" * 43
        with patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}), \
                patch.object(app, "EMBEDDED_SESSION_TOKEN", token), \
                patch.object(app, "load_env", return_value={"LLM_BACKEND": "agy"}), \
                patch.object(app.subprocess, "run") as run:
            status, body = self.request("GET", "/api/system/google_status",
                                        headers={"Cookie": "magi_session=" + token})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["status"], "disconnected")
            with self.assertRaisesRegex(RuntimeError, "unavailable in the standalone"):
                app.call_llm([{"role": "user", "content": "hello"}])
            with self.assertRaisesRegex(RuntimeError, "unavailable in the standalone"):
                app._llm_route_setup([{"role": "user", "content": "hello"}])
            run.assert_not_called()

    def test_oversized_request_is_rejected_before_body_read(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.putrequest("POST", "/api/system/command")
            connection.putheader("Content-Length", str(app.MAX_REQUEST_BYTES + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
