"""Package the edited Chinese translations and their source-aligned units."""
import hashlib
import html
import json
import re
import statistics
import zipfile
from pathlib import Path

import build_rules_document as original

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/wikipedia_zh_2026-11-10"
SOURCE = ROOT / "data/processed/wikipedia_2026-11-10"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
SOURCE_MARKER = "<!-- GENERATED_SOURCES -->"
BLOCK = re.compile(
    r"^### ([A-Z0-9-]+) ([^\n]+)\n\n来源标识：(wiki-[0-9a-z]+):L(\d+)-L(\d+)\n\n(.*?)(?=^#{1,3} |\Z)",
    re.M | re.S,
)


def write(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)


def hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inline(value):
    escaped = html.escape(value)
    escaped = re.sub(r"\[([^\]]+)\]\(([^\s]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_html(text):
    lines = text.splitlines()
    result = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.startswith("<!--"):
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level, label = len(heading[1]), heading[2]
            anchor = re.match(r"(L\d+[A-Z]?-\d+)\b", label)
            attr = ' id="' + anchor[1] + '"' if anchor else ""
            result.append("<h{0}{1}>{2}</h{0}>".format(level, attr, inline(label)))
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\|[ :|\-]+\|$", lines[index + 1]):
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            head = "<thead><tr>" + "".join("<th>" + inline(c) + "</th>" for c in rows[0]) + "</tr></thead>"
            body = "<tbody>" + "".join("<tr>" + "".join("<td>" + inline(c) + "</td>" for c in row) + "</tr>" for row in rows[1:]) + "</tbody>"
            result.append('<div class="table-wrap"><table>' + head + body + "</table></div>")
            continue
        if line.startswith("> "):
            notes = []
            while index < len(lines) and lines[index].startswith(">"):
                notes.append(lines[index].lstrip("> "))
                index += 1
            result.append('<aside class="review">' + inline("\n".join(notes)) + "</aside>")
            continue
        if line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append("<li>" + inline(lines[index][2:]) + "</li>")
                index += 1
            result.append("<ul>" + "".join(items) + "</ul>")
            continue
        parts = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#|>|\||- )", lines[index]):
            parts.append(lines[index])
            index += 1
        result.append("<p>" + inline("\n".join(parts)) + "</p>")
    return "\n".join(result)


STYLE = """
:root{color-scheme:light}body{margin:0;background:#f3f6fa;color:#1d2c3e;font-family:system-ui,'Microsoft YaHei',sans-serif;line-height:1.9;font-size:17px}main{max-width:1020px;margin:24px auto;background:#fff;padding:38px 48px;border-radius:14px}nav{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}nav a{padding:6px 12px;border:1px solid #d8e4ee;border-radius:6px;background:#f5faff}a{color:#126782;overflow-wrap:anywhere}h1,h2,h3{line-height:1.5;scroll-margin-top:24px}h1{font-size:30px}h2{font-size:25px;border-bottom:2px solid #e3eaf1;padding:20px 0 10px;margin-top:42px}h3{font-size:20px;color:#244c65;margin-top:34px}p{overflow-wrap:anywhere}aside.review{background:#fff7e5;border-left:4px solid #d29e34;padding:12px 18px;margin:16px 0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:15px}td,th{border:1px solid #d6dee8;padding:9px 12px;text-align:left}th{background:#eef5fa}.doc-section{margin-top:70px;border-top:4px solid #bfd5e3}code{background:#eef3f7;padding:2px 5px}@media(max-width:700px){main{padding:22px 18px;margin:0;border-radius:0}body{font-size:16px}}@media print{body{background:#fff;font-size:11pt}main{margin:0;padding:0;max-width:none}nav{display:none}.doc-section{page-break-before:always}h2,h3{page-break-after:avoid}tr{page-break-inside:avoid}}
"""


def page(title, body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>' + html.escape(title) + '</title><style>' + STYLE + '</style><main>' + body + '</main></html>\n'


def main():
    metadata = {d["source_id"]: d for d in json.loads((SOURCE / "sources.json").read_text(encoding="utf-8"))}
    chunks = []
    parallels = []
    documents = []
    for path in sorted(OUT.glob("[0-9][0-9]_*.md")):
        base = path.read_text(encoding="utf-8-sig").split(SOURCE_MARKER)[0].rstrip()
        title = base.splitlines()[0].lstrip("# ")
        doc_id = "football-zh-" + path.name[:2]
        source_ids = set()
        matches = list(BLOCK.finditer(base))
        if not matches:
            raise ValueError("No attributed translation blocks: " + path.name)
        for match in matches:
            block_id, label, sid, start, end, body = match.groups()
            start, end = int(start), int(end)
            body = body.strip()
            source_ids.add(sid)
            source = metadata[sid]
            numbered, _, _ = original.source_lines(sid.replace("wiki-", ""))
            original_lines = [(n, original.clean(v)) for n, v in sorted(numbered.items()) if start <= n <= end and v.strip() and not v.startswith(("[Button", "[Input", "[edit"))]
            if not original_lines:
                raise ValueError("Source range missing: " + block_id)
            en = "\n\n".join(value for _, value in original_lines)
            headings = re.findall(r"^## ([^\n]+)", base[:match.start()], re.M)
            section = headings[-1] if headings else title
            review = re.findall(r"^> 校核提示：(.*)$", body, re.M)
            if sid == "wiki-08b":
                review.append("来源坠球专题明确包含2019/2020年程序，不能自动当作现行赛季。")
            meta = {
                "document_id": doc_id, "document_title": title, "section_path": [title, section, label],
                "law_number": int(re.match(r"L(\d+)", block_id)[1]),
                "source_id": sid, "source_url": source["url"], "source_revision_id": source["revision_id"],
                "source_revision_status": source["revision_status"], "source_lines": [start, end],
                "source_attribution": "Wikipedia contributors", "contributors_url": source["contributors_url"],
                "license": "CC BY-SA 4.0", "license_url": LICENSE_URL,
                "translation_method": "AI Chinese translation with editorial selection; captions and some non-rule examples omitted",
                "official_translation": False, "expert_reviewed": False,
                "needs_rule_review": bool(review), "review_notes": review,
                "snapshot_date": "2026-11-10", "language": "zh-CN",
                "source_text_sha256": hash_text(en), "translated_body_sha256": hash_text(body),
            }
            text = title + "\n" + section + "\n" + block_id + " " + label + "\n\n" + body
            chunks.append({"id": block_id, "text": text, "metadata": meta})
            parallels.append({"id": block_id, "title_zh": label, "text_zh": body, "text_en": en, "metadata": meta})
        footer = [SOURCE_MARKER, "## 来源和版本", "以下版本号来自读取通道可见的页面页脚；历史版本 URL 未能全部独立回取。原始正文快照及本译文均另有本地 SHA-256 记录。"]
        for sid in sorted(source_ids):
            source = metadata[sid]
            footer.append("- " + sid + "： [" + source["title"] + "](" + source["url"] + ")；页面可见修订号 " + (source["revision_id"] or "未取得") + "；[作者贡献历史](" + source["contributors_url"] + ")。")
        full = base + "\n\n" + "\n\n".join(footer) + "\n"
        write(path, full)
        html_path = path.with_suffix(".html")
        write(html_path, page(title, markdown_html(full)))
        documents.append({"document_id": doc_id, "title": title, "markdown": path.name, "html": html_path.name, "blocks": len(matches), "source_ids": sorted(source_ids), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    ids = [c["id"] for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate stable block IDs")
    sizes = [len(p["text_zh"]) for p in parallels]
    chinese = sum(len(re.findall(r"[\u3400-\u9fff]", p["text_zh"])) for p in parallels)
    summary = {
        "documents": len(documents), "source_pages": len(metadata),
        "visible_revision_ids_available": sum(bool(s["revision_id"]) for s in metadata.values()),
        "translation_blocks": len(chunks), "translated_body_characters": sum(sizes), "chinese_han_characters": chinese,
        "median_block_characters": statistics.median(sizes), "max_block_characters": max(sizes),
        "blocks_with_review_notes": sum(c["metadata"]["needs_rule_review"] for c in chunks),
        "aligned_source_excerpt_characters": sum(len(p["text_en"]) for p in parallels),
        "translation_scope": "Selected rule-related excerpts, not the entire Wikipedia articles or an official rulebook",
        "unit": "characters, not model tokens", "date": "2026-11-10",
    }
    for filename, records in [("chunks_zh.jsonl", chunks), ("parallel_zh_en.jsonl", parallels)]:
        write(OUT / filename, "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n")
    write(OUT / "corpus_manifest.json", json.dumps({"summary": summary, "documents": documents, "sources": list(metadata.values())}, ensure_ascii=False, indent=2) + "\n")
    index = ["# 足球规则中文文档入口", "已整理为5份独立文档。正文为来源相关段落的中文翻译整理，非官方中文规则书；图片、部分历史、战术和重复举例被省略。", "英文原始快照仍保留。页面可见修订号已补齐至18/18；这不等于已核验所有历史版本原文或官方赛季效力。", "## 阅读文件"]
    for doc in documents:
        index.append("- [" + doc["title"] + "](" + doc["markdown"] + ")；[网页阅读版](" + doc["html"] + ")；" + str(doc["blocks"]) + "个知识段。")
    index.extend([
        "## 切分与导入", "每个三级标题下面是一段完整知识单元，使用稳定编号，如 L11-03。段落把条件、例外和校核提示一起保留。表格作为一个完整单元，不能按行任意拆开。",
        "已输出 chunks_zh.jsonl，可按每行一条知识段导入。text 字段只放中文及必要小标题；metadata 保存来源和版本，避免在生成上下文里重复塞入整篇英文。需要核对翻译时，再使用 parallel_zh_en.jsonl 的英中对照。",
        "本批共" + str(len(chunks)) + "个知识段，译文正文共" + str(sum(sizes)) + "字符，中位数每段" + str(statistics.median(sizes)) + "字符，最大" + str(max(sizes)) + "字符。这里按字符计数，不把字符数当成模型 token 数；接入指定模型后应以实际 tokenizer 检查限制。",
        "metadata.needs_rule_review 为 true 的段落带有来源简化、历史版本或待核对提示。制作正式现行规则评测时应先审校，不能把它们直接标为无条件真值。其余段落同样尚未由足球裁判专家审校。",
        "## 文件与版本", "corpus_manifest.json 记录每份文档校验值和18个来源的信息；各知识段另带对应原文范围和校验值。修改译文时，保持原有编号；确实拆段时添加子编号，并记录变更。",
        "## 许可和作者归属", "原文作者为 Wikipedia contributors。译文是 AI 翻译并作结构整理的改编文本，按 CC BY-SA 4.0 提供；保留来源与修改说明：https://creativecommons.org/licenses/by-sa/4.0/ 。原文中另有权利说明的第三方引用不因本整理而取得额外许可。",
    ])
    write(OUT / "00_阅读与切分说明.md", "\n\n".join(index) + "\n")
    nav = "<nav>" + "".join('<a href="#doc-' + str(i + 1) + '">' + str(i + 1) + ". " + html.escape(doc["title"].split("：")[-1]) + "</a>" for i, doc in enumerate(documents)) + "</nav>"
    combined = markdown_html("\n\n".join(index[:3])) + nav
    for i, doc in enumerate(documents):
        text = (OUT / doc["markdown"]).read_text(encoding="utf-8")
        combined += '<section class="doc-section" id="doc-' + str(i + 1) + '">' + markdown_html(text) + "</section>"
    write(OUT / "足球规则_中文阅读版.html", page("足球规则：五份中文规则文档", combined))
    archive = ROOT / "data/processed/足球规则中文语料包_2026-11-10.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(OUT.iterdir()):
            if path.is_file():
                bundle.write(path, arcname=OUT.name + "/" + path.name)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
