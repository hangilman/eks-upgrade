"""Amazon EKS User Guide(awsdocs/amazon-eks-user-guide) 의 버전별 릴리스 노트 파싱."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import clean, section

_BASE = "https://raw.githubusercontent.com/awsdocs/amazon-eks-user-guide/mainline/latest/ug/versioning/"
DOCS = {
    "standard": (
        _BASE + "kubernetes-versions-standard.adoc",
        "https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html",
    ),
    "extended": (
        _BASE + "kubernetes-versions-extended.adoc",
        "https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-extended.html",
    ),
}


@dataclass
class EksNotes:
    important: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    subsections: list[tuple[str, str]] = field(default_factory=list)


def adoc_to_md(text: str) -> str:
    text = text.replace("{aws}", "AWS")
    text = re.sub(r"link:([^\[\s]+)\[([^,\]]*)[^\]]*\]", r"\2", text)
    text = re.sub(r"(https?://[^\s\[]+)\[([^\]]*)\]", lambda m: f"[{m.group(2) or m.group(1)}]({m.group(1)})", text)
    text = re.sub(r"<<[^,>]+,\s*([^>]+)>>", r"\1", text)
    text = re.sub(r"<<([^>]+)>>", r"\1", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"**\1**", text)  # adoc *bold* -> md **bold**
    return text


RELEASE_CALENDAR = "https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html#kubernetes-release-calendar"


def available_minors(doc: str) -> list[tuple[int, int]]:
    """문서에 섹션이 있는 Kubernetes 버전 목록 (예: [(1, 36), (1, 35)])."""
    return [(int(a), int(b)) for a, b in re.findall(r"^== Kubernetes (\d+)\.(\d+)\s*$", doc, flags=re.M)]


def find_section(doc: str, minor: str) -> str | None:
    return section(doc, rf"^== Kubernetes {re.escape(minor)}\s*$", r"^== [^=]")


def _items(lines: list[str]) -> list[str]:
    items: list[list[str]] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("[#") or s.startswith("["):
            continue
        if s.startswith("** "):
            if items:
                items[-1].append("— " + s[3:])
            continue
        if s.startswith("* "):
            items.append([s[2:]])
        elif s.startswith("Kubernetes `") and "is now available" in s:
            continue
        elif s.startswith("For the complete Kubernetes"):
            continue
        elif items:
            items[-1].append(s)
        else:
            items.append([s])
    return [clean(adoc_to_md(" ".join(i)), 700) for i in items]


def parse_section(sec: str) -> EksNotes:
    notes = EksNotes()
    main_part, *subs = re.split(r"^=== (.+)$", sec, flags=re.M)

    # [IMPORTANT] / [WARNING] ==== ... ==== 블록은 중요 공지로 분리
    important_lines: list[str] = []
    normal_lines: list[str] = []
    in_block = False
    block_kind = ""
    pending_kind = ""
    for line in main_part.splitlines():
        s = line.strip()
        if re.fullmatch(r"\[(IMPORTANT|WARNING|NOTE|TIP|CAUTION)\]", s):
            pending_kind = s[1:-1]
            continue
        if s == "====":
            if in_block:
                in_block = False
            else:
                in_block, block_kind = True, pending_kind
            pending_kind = ""
            continue
        if in_block and block_kind in ("IMPORTANT", "WARNING", "CAUTION"):
            important_lines.append(line)
        else:
            normal_lines.append(line)

    notes.important = _items(important_lines)
    notes.notes = _items(normal_lines)
    for title, body in zip(subs[0::2], subs[1::2]):
        body_lines = [ln for ln in body.splitlines() if ln.strip() != "===="]
        notes.subsections.append((title.strip(), " / ".join(_items(body_lines))))
    return notes
