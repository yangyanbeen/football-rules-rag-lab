"""Local Kotaemon reasoning overlay; the pinned upstream checkout stays clean."""

import json
from pathlib import Path

from kotaemon.base import Document
from ktem.reasoning.simple import FullQAPipeline

from football_evidence import ROOT, REFUSAL, get_engine, render_panel


class FootballEvidenceQAPipeline(FullQAPipeline):
    @classmethod
    def get_info(cls):
        return {
            "id": "simple",
            "name": "足球规则 · 证据问答",
            "description": "依据所选足球规则资料回答，保留原文条件，并显示可核对的逐段来源。",
        }

    def stream(self, message: str, conv_id: str, history: list, **kwargs):
        # Reuse the upstream user's selected-file retrieval boundary. Old answers
        # in history are deliberately not treated as evidence for this question.
        engine = get_engine()
        yield Document(channel="info", content=None)
        try:
            docs, _ = self.retrieve(message, history=[])
            allowed = engine.allowed_documents(docs)
            selected_model = self.answering_pipeline.llm.model
            if selected_model != engine.config["chat_model"]:
                raise ValueError("当前证据问答配置需要本地 ollama 模型 qwen2.5:3b，请在会话中选择 ollama。")
            result = engine.answer(message, allowed_document_ids=allowed)
            result["upstream_retrieved"] = [{"doc_id": doc.doc_id, "file_name": doc.metadata.get("file_name"), "file_id": doc.metadata.get("file_id")} for doc in docs]
            result["allowed_document_ids"] = sorted(allowed)
        except Exception as exc:
            result = {"question": message, "answer": REFUSAL, "status": "refused", "citations": [], "error": f"{type(exc).__name__}: {exc}"}
        # The UI receives only a complete, validated answer, never unchecked tokens.
        yield Document(channel="chat", content=result["answer"])
        yield Document(channel="info", content=render_panel(result))
        journal = ROOT / ".cache/football-quality/ui-events.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        print("Football evidence guard:", result["status"], [c["chunk_id"] for c in result["citations"]], result.get("error", ""))
        return Document(text=result["answer"], metadata={"citations": result["citations"], "profile": "evidence-guard-v1"})
