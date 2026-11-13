"""Release note 본문에서 업그레이드에 영향을 주는 항목을 규칙 기반으로 추출."""

from __future__ import annotations

import re

from .models import CRITICAL, INFO, REVIEW, SECURITY, Finding

# 이 제목 아래에 있는 항목은 모두 🔴 로 분류
CRITICAL_HEADING = re.compile(
    r"breaking|action required|upgrade notes?|urgent|important|attention|must read|notice", re.I
)
DEPRECATION_HEADING = re.compile(r"deprecat", re.I)
SECURITY_HEADING = re.compile(r"security|cve", re.I)

CRITICAL_TEXT = re.compile(
    r"breaking|action required|no longer support|not (?:be )?backward[s]? compatible|incompatib"
    r"|drop(?:ped|s)? support|minimum (?:supported )?(?:kubernetes|k8s|eks) version"
    r"|\b\w+(?:\([^)]*\))?!:",  # conventional commit breaking marker: feat!: / chore(x)!:
    re.I,
)
SECURITY_TEXT = re.compile(r"\bCVE-\d{4}-\d+|\bGHSA-|security (?:fix|patch|vulnerab)", re.I)
REVIEW_TEXT = re.compile(
    r"deprecat|\bremov(?:e|ed|es|ing)\b.*\b(?:flag|option|field|annotation|support|api|parameter|argument|env)"
    r"|default (?:value|behavio)|by default|changed? (?:the )?default|\brenam(?:e|ed)\b"
    r"|requires? (?:kubernetes|k8s|eks|iam)|iam (?:policy|permission)|migrat",
    re.I,
)

_HEADING_MD = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_HEADING_BOLD = re.compile(r"^\s*\*\*([^*]+)\*\*:?\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"</?(?:details|summary|br|p|div)[^>]*>", re.I)

NOISE = re.compile(
    r"^(?:full changelog|\*\*full changelog|new contributors|@\S+ made their first contribution|what's changed)",
    re.I,
)


def _clean(text: str, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def split_body(body: str) -> list[tuple[str, str]]:
    """본문을 (가장 가까운 제목, 항목 텍스트) 목록으로 분리."""
    body = _TAG.sub("", _HTML_COMMENT.sub("", body or ""))
    items: list[tuple[str, str]] = []
    heading = ""
    current: list[str] | None = None
    base_indent = 0

    def flush():
        nonlocal current
        if current:
            items.append((heading, " ".join(current)))
        current = None

    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if m := (_HEADING_MD.match(line) or _HEADING_BOLD.match(line)):
            flush()
            heading = m.group(1).strip()
            continue
        if m := _BULLET.match(line):
            indent = len(m.group(1))
            if current is not None and indent > base_indent:
                current.append(m.group(2))  # 하위 bullet 은 상위 항목에 합침
                continue
            flush()
            base_indent = indent
            current = [m.group(2)]
            continue
        if current is not None and line[:1].isspace():
            current.append(line.strip())  # 들여쓴 줄은 직전 bullet 의 연속
            continue
        flush()
        items.append((heading, line.strip()))  # bullet 아닌 단락
    flush()
    return [(h, t) for h, t in items if not NOISE.match(t) and len(t) > 3]


def classify_item(heading: str, text: str) -> str:
    if CRITICAL_HEADING.search(heading) or CRITICAL_TEXT.search(text):
        return CRITICAL
    if SECURITY_HEADING.search(heading) or SECURITY_TEXT.search(text):
        return SECURITY
    if DEPRECATION_HEADING.search(heading) or REVIEW_TEXT.search(text):
        return REVIEW
    return INFO


def classify_release(body: str, source: str = "", url: str = "") -> list[Finding]:
    return [
        Finding(severity=classify_item(h, t), text=_clean(t), source=source, url=url)
        for h, t in split_body(body)
    ]
