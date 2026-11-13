"""Markdown/AsciiDoc 섹션 추출 공통 유틸리티."""

from __future__ import annotations

import re


def section(text: str, start: str, end: str) -> str | None:
    """start 정규식과 일치하는 줄 다음부터 end 정규식과 일치하는 줄 전까지를 반환."""
    start_re, end_re = re.compile(start), re.compile(end)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if start_re.match(line):
            out = []
            for nxt in lines[i + 1 :]:
                if end_re.match(nxt):
                    break
                out.append(nxt)
            return "\n".join(out)
    return None


def bullet_items(block: str, bullet: str = r"[-*]") -> list[str]:
    """최상위 bullet(들여쓰기 0~1칸) 단위로 항목을 묶는다. 이어지는 줄은 같은 항목에 합친다."""
    top = re.compile(rf"^\s?{bullet}\s+(.*)$")
    items: list[list[str]] = []
    for line in block.splitlines():
        if m := top.match(line):
            items.append([m.group(1)])
        elif items and line.strip():
            items[-1].append(re.sub(r"^[-*]\s+", "— ", line.strip()))
    return [" ".join(i) for i in items]


def clean(text: str, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # "([#123](url), [@user](url)) [SIG Node]" -> "([#123](url))"
    text = re.sub(r"\(\[#(\d+)\]\(([^)]+)\)(?:,\s*\[@[^\]]+\]\([^)]+\))+\)", r"([#\1](\2))", text)
    text = re.sub(r"\s*\[SIG [^\]]+\]\s*$", "", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
