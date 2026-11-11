"""Build an attributed rules reader from saved web-reader text snapshots.

This script uses local files only. Source snapshots may be excerpts rather than
complete pages; missing MediaWiki revision IDs are deliberately left blank.
"""
import csv
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-11-10"
RAW = ROOT / "data" / "raw" / ("wikipedia_" + STAMP)
OUT = ROOT / "data" / "processed" / ("wikipedia_" + STAMP)
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
COLLECTION = ROOT / "data" / "manifests" / ("wiki_collection_" + STAMP + ".json")


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean(value):
    value = re.sub(r"\^\{[^}]*\}", "", value)
    value = re.sub(r"【\d+†([^】]*)】", lambda m: m.group(1), value)
    value = re.sub(r"【[^】]*】", "", value)
    return value.strip()


def source_lines(source_id):
    paths = sorted(RAW.glob(source_id + "*.web.txt"))
    numbered = {}
    combined = []
    for path in paths:
        raw = path.read_text(encoding="utf-8-sig")
        combined.append(raw)
        for line in raw.splitlines():
            match = re.match(r"^L(\d+): ?(.*)$", line)
            if match:
                number, value = int(match[1]), match[2]
                if number not in numbered or len(value) > len(numbered[number]):
                    numbered[number] = value
    return numbered, "\n".join(combined), paths


def current_rules(source_id, numbered):
    entries = sorted(numbered.items())
    if source_id == "03":
        selected = []
        active = False
        for number, value in entries:
            if value.startswith("### Players, equipment, and officials") or value.startswith("### Duration and tie-breaking methods"):
                active = True
            elif re.match(r"^#{1,3} ", value):
                active = False
            if active:
                selected.append((number, value))
        entries = selected
    else:
        appearances = [number for number, value in entries if value == "Appearance"]
        if appearances:
            entries = [(number, value) for number, value in entries if number > appearances[-1]]

    skip_level = None
    result = []
    numbers = []
    for number, raw in entries:
        value = clean(raw)
        heading = re.match(r"^(#{1,6})\s+(.+)$", value)
        if heading:
            level = len(heading[1])
            title = heading[2].lower()
            if skip_level is not None:
                if level <= skip_level:
                    skip_level = None
                else:
                    continue
            if title in {"references", "notes", "footnotes", "see also", "external links", "bibliography", "further reading"}:
                break
            if any(token in title for token in ["history", "before 1863", "strategy", "tactics", "statistics", "motivation", "notable examples", "frequency", "suppliers", "unicode"]):
                skip_level = level
                continue
        if skip_level is not None:
            continue
        if any(token in value for token in ["Retrieved from", "This page was last edited", "Text is available under"]):
            break
        if value.startswith(("[Input", "[Button", "[edit", "Main article:", "Further information:", "See also:", "For other uses", "This article", "From Wikipedia")):
            continue
        if "This article needs" in value or value.startswith("(Redirected from") or re.match(r"^For .+ see ", value):
            continue
        if not value or "†Image" in raw or "redirects here" in value:
            continue
        if value in {"Appearance", "Contents", "Loading", "edit", "edit source"}:
            continue
        if heading:
            value = "#" + value  # reserve H2 for the source chapter itself
        result.append(value)
        numbers.append(number)
    return "\n\n".join(result).strip(), numbers


def render_markdown(text):
    chunks = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        escaped = html.escape(block)
        escaped = re.sub(r"\[([^\]]+)\]\((https?://[^\s]+)\)", r'<a href="\2">\1</a>', escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        heading = re.match(r"^(#{1,6}) (.*)$", escaped, re.S)
        if heading:
            level = len(heading[1])
            chunks.append("<h{0}>{1}</h{0}>".format(level, heading[2]))
        else:
            chunks.append("<p>" + escaped.replace("\n", "<br>\n") + "</p>")
    return "\n".join(chunks)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = json.loads(COLLECTION.read_text(encoding="utf-8"))["sources"]
    metadata = []
    documents = []
    cover = [
        "# 足球规则资料：网站正文采集版",
        "采集日期：2026-11-10｜来源：英文 Wikipedia｜正文语言：英文｜中文目录与来源说明",
        "这份资料从网站实际读取的文本整理而成，包含规则总览和 17 条规则所对应的 18 个来源页面的正文摘取。它不是 IFAB 官方规则书，也不对应一个已经核定的官方赛季版本；适合作为足球知识阅读和 RAG 检索实验的初始语料。",
        "每章列出原网页、作者贡献历史和可取得的版本信息。网站历史沿革、策略、统计、导航和图片被省略；少数专题与正式规则条款的覆盖范围并不完全一致。原始采集文本另外保存在本项目 data/raw/ 目录。",
        "许可：Wikipedia contributors；条目文本依据 CC BY-SA 4.0 使用，第三方引用或另有声明的内容保留其原有权利。整理改动为删除导航、图片与非规则章节、保留英文正文、增加中文目录和来源元数据。",
        "许可链接：[CC BY-SA 4.0](" + LICENSE + ")。若公开分享这份整理文本，请保留作者归属、原文链接、许可和修改说明，并遵守相同方式共享要求。",
        "获取说明：本机无法直连 Wikimedia API，本次经网页读取通道获取页面文本；该通道可能使用缓存。未取得的 revision ID 留空，以本地文本 SHA-256 固定本次语料快照。",
        "## 目录",
        "\n".join(str(i + 1) + ". " + source["label"] for i, source in enumerate(sources)),
    ]
    chapters = []
    for source in sources:
        numbered, raw, paths = source_lines(source["id"])
        text, used = current_rules(source["id"], numbered)
        if len(text) < 200:
            raise RuntimeError("Insufficient rule text for " + source["id"])
        url = "https://en.wikipedia.org/wiki/" + quote(source["slug"], safe="_")
        history = "https://en.wikipedia.org/w/index.php?title=" + quote(source["slug"], safe="_") + "&action=history"
        revisions = sorted(set(re.findall(r"oldid=(\d+)", raw)))
        revision = revisions[0] if len(revisions) == 1 else ""
        record = {
            "source_id": "wiki-" + source["id"], "title": source["slug"].replace("_", " "),
            "label_zh": source["label"], "language": "en", "url": url,
            "revision_id": revision, "acquired_date": STAMP,
            "revision_status": "reader footer ID; exact revision not independently fetched" if revision else "not obtained",
            "acquisition_method": "web_reader_extracted_text",
            "raw_sha256": sha(raw), "text_sha256": sha(text), "characters": len(text),
            "license": "CC BY-SA 4.0", "license_url": LICENSE,
            "attribution": "Wikipedia contributors", "contributors_url": history,
            "raw_files": [str(path.relative_to(ROOT)).replace("\\", "/") for path in paths],
            "included_source_lines": used, "scope": "rule-related excerpts, not a complete official rulebook",
        }
        metadata.append(record)
        documents.append(dict(record, text=text))
        version = "页面可见 revision：" + revision if revision else "页面 revision 未取得；本地正文 SHA-256：" + record["text_sha256"]
        chapters.extend([
            "## " + source["label"],
            "原条目：[" + record["title"] + "](" + url + ")｜[作者贡献历史](" + history + ")｜CC BY-SA 4.0",
            version,
            text,
        ])
    full = "\n\n".join(cover + chapters) + "\n"
    md_path = OUT / "足球规则资料_网站采集版.md"
    md_path.write_text(full, encoding="utf-8")
    style = "body{max-width:1000px;margin:35px auto;padding:0 28px;font:17px/1.75 system-ui,'Microsoft YaHei',sans-serif;color:#1c2738}h1,h2,h3{line-height:1.35}h2{margin-top:48px;border-bottom:2px solid #dfe6ee;padding-bottom:12px}a{color:#136b82;overflow-wrap:anywhere}p{white-space:normal;overflow-wrap:anywhere}@media print{body{font-size:11pt;margin:0;max-width:none}h2{page-break-before:always}h2,h3{page-break-after:avoid}}"
    html_text = '<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8"><title>足球规则资料：网站采集版</title><style>' + style + '</style><body>' + render_markdown(full) + '</body></html>'
    (OUT / "足球规则资料_网站采集版.html").write_text(html_text, encoding="utf-8")
    (OUT / "source_documents.jsonl").write_text("\n".join(json.dumps(doc, ensure_ascii=False) for doc in documents) + "\n", encoding="utf-8")
    (OUT / "sources.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["source_id", "title", "language", "url", "revision_id", "acquired_date", "text_sha256", "characters", "license", "license_url", "contributors_url", "acquisition_method"]
    with (ROOT / "data" / "manifests" / "sources.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(metadata)
    summary = {"source_count": len(metadata), "body_characters": sum(x["characters"] for x in metadata), "document_bytes": md_path.stat().st_size, "markdown_sha256": hashlib.sha256(md_path.read_bytes()).hexdigest(), "output_directory": str(OUT)}
    (OUT / "collection_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
