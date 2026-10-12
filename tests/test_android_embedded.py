"""Checks for the standalone Android packaging boundary and Python entrypoint."""

import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android_host"


class AndroidEmbeddedTests(unittest.TestCase):
    def test_matching_pixi_csp_patch_is_bundled_before_live2d(self):
        patch_file = ROOT / "pixi-unsafe-eval.min.js"
        license_file = ROOT / "pixi-unsafe-eval.LICENSE"
        self.assertIn("@pixi/unsafe-eval - v5.3.12",
                      patch_file.read_text(encoding="utf-8")[:100])
        self.assertIn("The MIT License", license_file.read_text(encoding="utf-8"))
        for page in ("index.html", "pet.html"):
            with self.subTest(page=page):
                html = (ROOT / page).read_text(encoding="utf-8")
                self.assertLess(html.index('/pixi.min.js?v=5'),
                                html.index('/pixi-unsafe-eval.min.js?v=5.3.12'))
                self.assertLess(html.index('/pixi-unsafe-eval.min.js?v=5.3.12'),
                                html.index('/pixi-live2d-display.min.js?v=4'))

    def test_pet_has_transparent_character_only_surface(self):
        html = (ROOT / "pet.html").read_text(encoding="utf-8")
        self.assertIn("background: transparent !important", html)
        self.assertIn("#wrap {", html)
        self.assertIn("background: transparent;", html)
        self.assertNotIn('id="bar"', html)
        self.assertNotIn('id="bubble"', html)
        self.assertNotIn("box-shadow:", html)
        self.assertNotIn("border-radius: 18px", html)
        self.assertIn("resolution: Math.min(window.devicePixelRatio || 1, 3)", html)

    def test_embedded_scene_background_is_separate_from_live2d_and_bundled(self):
        image = ROOT / "companion-room-night.png"
        self.assertTrue(image.is_file())
        self.assertGreater(image.stat().st_size, 100_000)
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        scene = css.split("html.embedded-host .avatar-custom-bg {", 1)[1].split("}", 1)[0]
        self.assertIn("background-image: url('/companion-room-night.png')", scene)
        self.assertIn("opacity: var(--avatar-bg-opacity, 1);", scene)
        self.assertIn("brightness(var(--avatar-bg-brightness, 1))", scene)
        gradle = (ANDROID / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("'companion-room-night.png'", gradle)
        backend = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('"companion-room-night.png"', backend)
        self.assertIn('"/companion-room-night.png"', backend)

    def test_embedded_server_avoids_an_occupied_fixed_port(self):
        import app

        with socket.socket() as blocker, \
                patch.dict(os.environ, {"MICRO_AGI_EMBEDDED": "1"}):
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            occupied_port = blocker.getsockname()[1]
            with patch.object(app, "PORT", occupied_port):
                server = app.create_embedded_server()
                try:
                    self.assertEqual(server.server_address[0], "127.0.0.1")
                    self.assertNotEqual(server.server_address[1], occupied_port)
                    self.assertEqual(app.PORT, server.server_address[1])
                finally:
                    server.server_close()

    def test_bundle_uses_explicit_allowlist_without_private_files(self):
        gradle = (ANDROID / "app" / "build.gradle").read_text(encoding="utf-8")
        allowed = gradle.split("def embeddedFiles = [", 1)[1].split("\n]", 1)[0]
        self.assertIn("'app.py'", allowed)
        self.assertIn("'db.py'", allowed)
        self.assertIn("'index.html'", allowed)
        self.assertNotIn("**", allowed)
        paths = re.findall(r"'([^']+)'", allowed)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all((ROOT / path).is_file() for path in paths))
        for private in (".env", "micro_agi.db", "mcp_config.json", "app.run.log"):
            self.assertNotIn("'" + private + "'", allowed)
        self.assertIn("id 'com.chaquo.python'", gradle)
        self.assertIn("prepareEmbeddedPython", gradle)
        app_ast = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        runtime_assets = next(
            ast.literal_eval(node.value) for node in app_ast.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "EMBEDDED_BUNDLE_ASSETS"
                    for target in node.targets))
        self.assertEqual(set(runtime_assets), {path for path in paths if not path.endswith(".py")})

    def test_embedded_entry_sets_private_data_path_before_import(self):
        entry = ANDROID / "app" / "src" / "main" / "python" / "mobile_entry.py"
        spec = importlib.util.spec_from_file_location("mobile_entry_test", entry)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        started = threading.Event()
        release = threading.Event()
        fake_app = types.ModuleType("app")

        fake_server = types.SimpleNamespace(server_address=("127.0.0.1", 45678))
        fake_app.create_embedded_server = lambda: fake_server

        def fake_run_server(server):
            self.assertIs(server, fake_server)
            started.set()
            release.wait(timeout=2)

        fake_app.run_server = fake_run_server
        received_tokens = []
        fake_app.set_embedded_session_token = received_tokens.append
        with tempfile.TemporaryDirectory() as private_dir:
            with patch.dict(os.environ, {"HOME": private_dir}, clear=False), \
                    patch.dict(sys.modules, {"app": fake_app}):
                endpoint = json.loads(module.start())
                token = endpoint["token"]
                self.assertTrue(started.wait(timeout=1))
                self.assertEqual(os.environ["MICRO_AGI_DATA_DIR"], private_dir)
                self.assertEqual(os.environ["MICRO_AGI_EMBEDDED"], "1")
                self.assertGreaterEqual(len(token), 40)
                self.assertEqual(endpoint["port"], 45678)
                self.assertEqual(received_tokens, [token])
                self.assertNotIn("MICRO_AGI_SESSION_TOKEN", os.environ)
                first_thread = module._server_thread
                self.assertEqual(json.loads(module.start()), endpoint)
                self.assertIs(module._server_thread, first_thread)
                release.set()
                first_thread.join(timeout=2)

    def test_fresh_embedded_import_serves_private_session_and_assets(self):
        probe = textwrap.dedent("""
            import hmac
            import http.client
            import importlib.util
            import json
            import os
            from pathlib import Path
            import sys
            import threading
            from unittest.mock import patch

            root = Path(sys.argv[1])
            sys.path.insert(0, str(root))
            entry = root / 'android_host/app/src/main/python/mobile_entry.py'
            spec = importlib.util.spec_from_file_location('mobile_entry_probe', entry)
            mobile_entry = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mobile_entry)
            assert 'app' not in sys.modules

            class DeferredThread:
                def __init__(self, target, **kwargs):
                    self.target = target
                def start(self):
                    pass
                def is_alive(self):
                    return True

            with patch.object(threading, 'Thread', DeferredThread):
                endpoint = json.loads(mobile_entry.start())
                token = endpoint['token']
                port = endpoint['port']
            import app
            import db
            assert db.DB_PATH == str(Path(os.environ['HOME']) / 'micro_agi.db')
            assert Path(db.DB_PATH).is_file()
            assert app.EMBEDDED_SESSION_TOKEN == token
            assert app.PORT == port

            server = mobile_entry._server
            assert server.server_address == ('127.0.0.1', port)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            def request(path, headers=None):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=2)
                try:
                    conn.request('GET', path, headers=headers or {})
                    response = conn.getresponse()
                    return response.status, response.read()
                finally:
                    conn.close()
            try:
                status, body = request('/api/health')
                health = json.loads(body)
                assert status == 200 and health['embedded'] is True
                assert health['ok'] is True and health['ready'] is True
                assert health['port'] == port
                expected = hmac.new(token.encode('ascii'),
                                    b'micro-agi-embedded-health-v1', 'sha256').hexdigest()
                assert health['proof'] == expected
                assert token.encode() not in body
                assert request('/api/projects')[0] == 403
                assert request('/google_login')[0] == 501
                assert request('/api/projects', {'Cookie': 'magi_session=' + token})[0] == 200
                status, body = request('/api/aios/status',
                    {'Cookie': 'magi_session=' + token,
                     'Origin': 'http://127.0.0.1:' + str(port)})
                assert status == 200
                assert json.loads(body)['panel'] == 'http://127.0.0.1:' + str(port) + '/'
                if port != 8087:
                    assert request('/api/projects',
                        {'Cookie': 'magi_session=' + token,
                         'Origin': 'http://127.0.0.1:8087'})[0] == 403
                app.set_embedded_session_token('z' * 43)
                assert request('/api/projects', {'Cookie': 'magi_session=' + token})[0] == 403
                assert request('/api/projects', {'Cookie': 'magi_session=' + 'z' * 43})[0] == 200
                for asset in ('/', '/script.js', '/style.css', '/pet.html'):
                    status, body = request(asset)
                    assert status == 200 and body, asset
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)
        """)
        with tempfile.TemporaryDirectory() as private_dir:
            env = os.environ.copy()
            env["HOME"] = private_dir
            env["USERPROFILE"] = private_dir
            env.pop("MICRO_AGI_EMBEDDED", None)
            env.pop("MICRO_AGI_DATA_DIR", None)
            result = subprocess.run(
                [sys.executable, "-c", probe, str(ROOT)], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
