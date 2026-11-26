"""Contract tests for the transport/session layer (no model call required)."""
from __future__ import annotations

import importlib
import os
import unittest
from pathlib import Path

class ApiContractTest(unittest.TestCase):
    def test_session_isolation_and_chat_persistence(self):
        old_db = os.environ.get("FOOTBALL_API_DB")
        os.environ["FOOTBALL_API_DB"] = str(Path(__file__).resolve().parents[1] / ".runtime" / "task13-api" / "test-contract.sqlite3")
        try:
            self._run_session_contract()
        finally:
            if old_db is None:
                os.environ.pop("FOOTBALL_API_DB", None)
            else:
                os.environ["FOOTBALL_API_DB"] = old_db

    def _run_session_contract(self):
        import backend.api_app as api
        api = importlib.reload(api)

        def fake_worker(question, check=False, *, history=()):
            return ({
                "trace_id": "a" * 32,
                "status": "answered",
                "answer": "已回答。",
                "citations": [], "selected_ids": [], "offered_ids": [], "retrieved_ids": [],
                "refusal_reason": None, "error": None,
                "timing": {"retrieval_seconds": 0, "generation_seconds": 0, "total_seconds": 0},
                "query_resolution": {"history_turns": len(history)},
            }, "private", 0.01)

        original_worker = api.call_worker
        api.call_worker = fake_worker
        try:
            api.startup()
            first = api.create_session()
            session_id = first["session_id"]
            response = api.chat(api.ChatRequest(session_id=session_id, question="第一问"))
            self.assertEqual(response["history_turns_used"], 0)
            second = api.chat(api.ChatRequest(session_id=session_id, question="第二问"))
            self.assertEqual(second["history_turns_used"], 1)
            isolated = api.chat(api.ChatRequest(question="新会话"))
            self.assertEqual(isolated["history_turns_used"], 0)
            details = api.get_session(session_id)
            self.assertEqual(len(details["turns"]), 2)
            # The HTTP boundary passes only the recent bounded window to the
            # worker; older turns stay persisted for audit/history display.
            for index in range(4):
                api._save_turn(session_id, f"旧问题{index}", {"answer": "回答。", "status": "answered", "trace_id": "b" * 32})
            self.assertEqual([pair[0] for pair in api._history(session_id)], ["旧问题1", "旧问题2", "旧问题3"])
            original_worker = api.call_worker
            api.call_worker = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated timeout"))
            with self.assertRaises(api.HTTPException) as failure:
                api.chat(api.ChatRequest(session_id=session_id, question="超时后恢复"))
            self.assertEqual(failure.exception.status_code, 503)
            api.call_worker = original_worker
            api.delete_session(session_id)
            with self.assertRaises(Exception):
                api.get_session(session_id)
        finally:
            api.call_worker = original_worker
