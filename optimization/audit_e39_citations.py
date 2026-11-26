"""Create a per-citation support audit from the completed E39 run.

This consumes the existing source-review ledger through E39's scored metrics;
it does not call a model or change the retrieval/answer path.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "optimization" / "reports" / "E39_live90_metrics.json"
OUT_MD = ROOT / "optimization" / "reports" / "E39_citation_audit.md"
OUT_JSON = ROOT / "optimization" / "reports" / "E39_citation_audit.json"


def main() -> None:
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    cases = [row for row in payload["cases"] if row["variant"] == "candidate"]
    rows = []
    by_chunk: dict[str, Counter] = defaultdict(Counter)
    for row in cases:
        selected = list(row.get("selected_ids") or [])
        supported = set(row.get("supported_citation_ids") or [])
        for chunk_id in selected:
            ok = chunk_id in supported
            by_chunk[chunk_id]["total"] += 1
            by_chunk[chunk_id]["supported"] += int(ok)
            rows.append({
                "question_id": row["question_id"],
                "chunk_id": chunk_id,
                "directly_supported": ok,
                "grade": row["grade"],
                "status": row["status"],
            })
    supported_count = sum(int(row["directly_supported"]) for row in rows)
    total_count = len(rows)
    summary = {
        "run": "E39_fixed90_python",
        "source_metrics": METRICS.relative_to(ROOT).as_posix(),
        "scope": "逐条引用与原文支持关系；沿用已登记的 source review，不新增模型或专家判断",
        "supported": supported_count,
        "total": total_count,
        "rate": supported_count / total_count if total_count else 0.0,
        "unsupported_count": total_count - supported_count,
        "rows": rows,
        "by_chunk": {k: dict(v) for k, v in sorted(by_chunk.items())},
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# E39 逐条引用支持审计",
        "",
        "本报告只检查最终选中段是否在既有 source-review 台账中被判定为直接支持；不把“答案看起来正确”当作引用支持，也不新增模型调用。",
        "",
        f"- 范围：90 题真实 E39 Worker 结果",
        f"- 直接支持：**{supported_count}/{total_count}（{supported_count / total_count:.2%}）**",
        f"- 未直接支持：{total_count - supported_count} 条",
        "",
        "## 按段统计",
        "",
        "| 段 ID | 直接支持 | 引用总数 | 支持率 |",
        "|---|---:|---:|---:|",
    ]
    for chunk_id, stats in sorted(by_chunk.items()):
        total = stats["total"]
        lines.append(f"| {chunk_id} | {stats['supported']} | {total} | {stats['supported'] / total:.2%} |")
    lines += ["", "## 未直接支持的逐条记录", "", "| 题号 | 段 ID | 评分 | 状态 |", "|---|---|---|---|"]
    for row in rows:
        if not row["directly_supported"]:
            lines.append(f"| {row['question_id']} | {row['chunk_id']} | {row['grade']} | {row['status']} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("supported", "total", "rate", "unsupported_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
