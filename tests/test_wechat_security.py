"""Security checks for the optional WeChat remote-control entry point."""

import sys
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


fake_db = types.ModuleType("db")
fake_db.memory_prompt_block = lambda limit=24: ""
sys.modules.setdefault("db", fake_db)

import app  # noqa: E402


class WeChatSecurityTests(unittest.TestCase):
    def setUp(self):
        app.WECHAT_SESSIONS.clear()

    def test_unbound_sender_cannot_auto_bind_by_default(self):
        with patch.object(app, "ENV_VARS", {}), patch.object(app, "save_env_config") as save, patch.object(app, "call_llm") as llm:
            app.handle_async_wechat_msg("hello", "unbound", "", "")
        save.assert_not_called()
        llm.assert_not_called()
        self.assertNotIn("unbound", app.WECHAT_SESSIONS)

    def test_unrelated_reply_does_not_execute_pending_command(self):
        app.WECHAT_SESSIONS["bound"] = {
            "is_waiting_approval": True,
            "current_command": "echo approved-only",
            "messages": [],
            "steps": [],
        }
        settings = {"WXCLAW_DEFAULT_TO": "bound", "ENABLE_WECHAT_SYSTEM_COMMANDS": "true"}
        with patch.object(app, "ENV_VARS", settings), patch.object(app, "run_wechat_command") as command, patch.object(app, "run_wxclawbot_send") as send:
            app.handle_async_wechat_msg("some unrelated text", "bound", "", "")
        command.assert_not_called()
        self.assertTrue(app.WECHAT_SESSIONS["bound"]["is_waiting_approval"])
        self.assertIn("确认", send.call_args.args[1])

    def test_wechat_command_execution_disabled_by_default(self):
        with patch.object(app, "ENV_VARS", {}), patch.object(app.subprocess, "run") as command:
            result = app.run_wechat_command("echo unsafe", {"steps": []})
        command.assert_not_called()
        self.assertIn("disabled", result)

    def test_concurrent_confirmations_execute_pending_command_once(self):
        app.WECHAT_SESSIONS["bound"] = {
            "is_waiting_approval": True,
            "current_command": "echo once",
            "messages": [],
            "steps": [],
        }
        entered_command = threading.Event()
        release_command = threading.Event()

        def fake_command(command, session):
            entered_command.set()
            self.assertTrue(release_command.wait(2))
            return "[Command completed]"

        settings = {"WXCLAW_DEFAULT_TO": "bound", "ENABLE_WECHAT_SYSTEM_COMMANDS": "true"}
        with patch.object(app, "ENV_VARS", settings), patch.object(app, "run_wechat_command", side_effect=fake_command) as command, patch.object(app, "call_llm", return_value="Done") as llm, patch.object(app, "run_wxclawbot_send") as send:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(app.handle_async_wechat_msg, "确认", "bound", "", "")
                self.assertTrue(entered_command.wait(2))
                second = pool.submit(app.handle_async_wechat_msg, "确认", "bound", "", "")
                release_command.set()
                first.result(timeout=2)
                second.result(timeout=2)

        command.assert_called_once()
        llm.assert_called_once()
        self.assertIn("没有待审批命令", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
