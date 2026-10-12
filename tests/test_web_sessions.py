"""Regression tests for chat-scoped command approval state."""

import sys
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


# Importing the HTTP module should not initialize the user's real database.
fake_db = types.ModuleType("db")
fake_db.memory_prompt_block = lambda limit=24: ""
sys.modules["db"] = fake_db

import app  # noqa: E402


class WebSessionTests(unittest.TestCase):
    def setUp(self):
        with app.WEB_SESSIONS_LOCK:
            app.WEB_SESSIONS.clear()

    def test_nonstream_approval_only_changes_matching_chat(self):
        with patch.object(app, "call_llm", side_effect=[
            "<execute>echo first</execute>",
            "<execute>echo second</execute>",
            "First command declined.",
        ]):
            first = app.start_agent_run("first", [], chat_id="chat-one")
            second = app.start_agent_run("second", [], chat_id="chat-two")
            self.assertEqual(first["command"], "echo first")
            self.assertEqual(second["command"], "echo second")
            self.assertIn("error", app.resume_agent_run(False, chat_id="wrong-chat"))
            result = app.resume_agent_run(False, chat_id="chat-one")

        self.assertEqual(result["status"], "completed")
        self.assertFalse(app.find_web_session("chat-one")["is_waiting"])
        self.assertTrue(app.find_web_session("chat-two")["is_waiting"])
        self.assertEqual(app.find_web_session("chat-two")["current_command"], "echo second")

    def test_stream_approval_only_changes_matching_chat(self):
        def fake_stream(messages):
            content = messages[-1]["content"]
            if content == "first":
                yield "<execute>echo first</execute>"
            elif content == "second":
                yield "<execute>echo second</execute>"
            else:
                yield "Command declined."

        with patch.object(app, "call_llm_stream", side_effect=fake_stream):
            list(app.start_agent_run_stream("first", [], chat_id="chat-one"))
            list(app.start_agent_run_stream("second", [], chat_id="chat-two"))
            wrong = list(app.resume_agent_run_stream(False, chat_id="wrong-chat"))
            result = list(app.resume_agent_run_stream(False, chat_id="chat-one"))

        self.assertEqual(wrong[0]["type"], "error")
        self.assertEqual(result[-1]["status"], "completed")
        self.assertFalse(app.find_web_session("chat-one")["is_waiting"])
        self.assertTrue(app.find_web_session("chat-two")["is_waiting"])

    def test_partial_model_failure_is_error_not_completed_answer(self):
        def failing_stream(_messages):
            yield "已收到的前半段"
            raise RuntimeError("secret upstream detail")

        session = {"messages": [{"role": "user", "content": "test"}], "is_waiting": True}
        with patch.object(app, "call_llm_stream", side_effect=failing_stream):
            events = list(app.process_next_llm_step_stream(session))

        self.assertEqual([event["type"] for event in events], ["token", "error"])
        self.assertEqual(events[0]["text"], "已收到的前半段")
        self.assertNotIn("secret upstream detail", events[1]["error"])
        self.assertFalse(session["is_waiting"])
        self.assertEqual(len(session["messages"]), 1)

    def test_embedded_model_command_never_opens_approval_or_retries(self):
        output = "我来帮你。<execute>echo should-not-run</execute>"
        session = {"messages": [{"role": "user", "content": "test"}],
                   "steps": [], "is_waiting": False, "project_id": "", "chat_id": ""}
        with patch.object(app, "embedded_mode", return_value=True), \
                patch.object(app, "call_llm", return_value=output) as model:
            result = app.process_next_llm_step(session)
        self.assertEqual(result["status"], "completed")
        self.assertIn("本次未执行任何命令", result["response"])
        self.assertNotIn("should-not-run", result["response"])
        self.assertFalse(session["is_waiting"])
        model.assert_called_once()

        stream_session = {"messages": [{"role": "user", "content": "test"}],
                          "steps": [], "is_waiting": False, "project_id": "", "chat_id": ""}
        with patch.object(app, "embedded_mode", return_value=True), \
                patch.object(app, "call_llm_stream", return_value=iter([output])) as stream_model:
            events = list(app.process_next_llm_step_stream(stream_session))
        self.assertEqual([event["type"] for event in events], ["token", "done"])
        self.assertEqual(events[-1]["status"], "completed")
        self.assertIn("本次未执行任何命令", events[-1]["response"])
        self.assertNotIn("should-not-run", events[-1]["response"])
        self.assertFalse(stream_session["is_waiting"])
        stream_model.assert_called_once()

    def test_nonstream_model_failure_is_not_completed_or_leaked(self):
        session = {"messages": [{"role": "user", "content": "test"}],
                   "steps": [], "is_waiting": True}
        with patch.object(app, "call_llm", side_effect=RuntimeError("secret upstream detail")):
            result = app.process_next_llm_step(session)
        self.assertEqual(result["status"], "error")
        self.assertNotIn("secret upstream detail", str(result))
        self.assertFalse(session["is_waiting"])
        self.assertEqual(len(session["messages"]), 1)

    def test_different_chats_can_progress_concurrently(self):
        first_started = threading.Event()
        release_first = threading.Event()

        def fake_llm(messages):
            content = messages[-1]["content"]
            if content == "first":
                first_started.set()
                self.assertTrue(release_first.wait(2))
            return f"<execute>echo {content}</execute>"

        with patch.object(app, "call_llm", side_effect=fake_llm):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(app.start_agent_run, "first", [], chat_id="chat-one")
                self.assertTrue(first_started.wait(2))
                second = pool.submit(app.start_agent_run, "second", [], chat_id="chat-two")
                self.assertEqual(second.result(timeout=2)["command"], "echo second")
                release_first.set()
                self.assertEqual(first.result(timeout=2)["command"], "echo first")


if __name__ == "__main__":
    unittest.main()
