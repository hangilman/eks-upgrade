"""리포트 Markdown -> HTML (웹 UI 용).

리포트는 이 도구가 생성하는 Markdown 이므로 사용하는 문법(제목, 목록, 표, 인용, 코드, 링크, 강조)만 지원한다.
외부 Release note 텍스트가 섞여 있으므로 모든 HTML 은 escape 하고, 링크는 http(s) 만 허용한다.
"""

from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM = re.compile(r"^(\s*)[-*]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _slug(text: str) -> str:
    return re.sub(r"[^\w가-힣-]+", "-", text.strip().lower()).strip("-")


def inline(text: str) -> str:
    tokens: list[str] = []

    def keep(fragment: str) -> str:
        tokens.append(fragment)
        return f"\x00{len(tokens) - 1}\x00"

    text = re.sub(r"(`+)(.+?)\1", lambda m: keep(f"<code>{html.escape(m.group(2).strip())}</code>"), text)
    text = html.escape(text, quote=False)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        return keep(f'<a href="{html.escape(html.unescape(url))}" target="_blank" rel="noopener noreferrer">') + label + keep("</a>")

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w])_([^_\n]+?)_(?![\w])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def render_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    depth = 0  # 열린 <ul> 수
    para: list[str] = []

    def close_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    def close_lists(to: int = 0):
        nonlocal depth
        while depth > to:
            out.append("</li></ul>")
            depth -= 1

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            close_para()
            close_lists()
            indent = len(line) - len(line.lstrip())
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i][indent:] if lines[i][:indent].strip() == "" else lines[i])
                i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(body))}</code></pre>")
            i += 1
            continue

        if not stripped:
            close_para()
            close_lists()
            i += 1
            continue

        if m := _HEADING.match(line):
            close_para()
            close_lists()
            level, text = len(m.group(1)), m.group(2)
            out.append(f'<h{level} id="{_slug(text)}">{inline(text)}</h{level}>')
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1].strip()):
            close_para()
            close_lists()
            head = _cells(line)
            out.append('<div class="table-wrap"><table><thead><tr>')
            out += [f"<th>{inline(c)}</th>" for c in head]
            out.append("</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in _cells(lines[i])) + "</tr>")
                i += 1
            out.append("</tbody></table></div>")
            continue

        if stripped.startswith(">"):
            close_para()
            close_lists()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue

        if m := _ITEM.match(line):
            close_para()
            level = len(m.group(1)) // 2 + 1
            text = m.group(2)
            if level > depth:
                while depth < level:
                    out.append("<ul>")
                    depth += 1
            else:
                close_lists(level)
                out.append("</li>")
            if cb := re.match(r"^\[( |x)\]\s+(.*)$", text):
                checked = " checked" if cb.group(1) == "x" else ""
                out.append(f'<li class="task"><label><input type="checkbox"{checked}> {inline(cb.group(2))}</label>')
            else:
                out.append(f"<li>{inline(text)}")
            i += 1
            continue

        if depth:  # 목록 항목의 이어지는 줄
            out.append(" " + inline(stripped))
        else:
            para.append(stripped)
        i += 1

    close_para()
    close_lists()
    return "\n".join(out)
