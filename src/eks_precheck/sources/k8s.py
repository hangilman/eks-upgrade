"""Kubernetes 업스트림 CHANGELOG / Deprecation Guide 파싱."""

from __future__ import annotations

import re

from ..models import RemovedApi
from .text import bullet_items, clean, section

CHANGELOG_RAW = "https://raw.githubusercontent.com/kubernetes/kubernetes/master/CHANGELOG/CHANGELOG-{minor}.md"
CHANGELOG_WEB = "https://github.com/kubernetes/kubernetes/blob/master/CHANGELOG/CHANGELOG-{minor}.md"
DEPRECATION_GUIDE_RAW = (
    "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/reference/using-api/deprecation-guide.md"
)
DEPRECATION_GUIDE_WEB = "https://kubernetes.io/docs/reference/using-api/deprecation-guide/"

# API Change 항목은 양이 많으므로 영향이 큰 것만 남긴다
_API_CHANGE_FILTER = re.compile(r"remov|deprecat|no longer|breaking|action required|stop(?:ped)? serving", re.I)


def release_section(changelog: str, minor: str) -> str | None:
    """CHANGELOG-1.31.md 에서 '# v1.31.0' 섹션(= 직전 마이너 대비 전체 변경)을 추출."""
    return section(changelog, rf"^# v{re.escape(minor)}\.0\s*$", r"^# v")


def urgent_notes(release: str) -> list[str]:
    block = section(release, r"^## Urgent Upgrade Notes", r"^## (?!#)")
    if not block:
        return []
    return [clean(i) for i in bullet_items(block)]


def kind_items(release: str, kind: str) -> list[str]:
    block = section(release, rf"^### {re.escape(kind)}\s*$", r"^#{1,3} ")
    if not block:
        return []
    return [clean(i) for i in bullet_items(block)]


def api_changes(release: str) -> list[str]:
    return [i for i in kind_items(release, "API Change") if _API_CHANGE_FILTER.search(i)]


def removed_apis(guide: str, minor: str) -> list[RemovedApi]:
    """deprecation-guide.md 의 '### v1.32' 섹션에서 제거되는 API 목록을 추출."""
    block = section(guide, rf"^### v{re.escape(minor)}\s*$", r"^#{2,3} ")
    if not block:
        return []
    result: list[RemovedApi] = []
    parts = re.split(r"^#### (.+?)\s*(?:\{#[^}]*\})?\s*$", block, flags=re.M)
    # parts = [prefix, title1, body1, title2, body2, ...]
    for title, body in zip(parts[1::2], parts[2::2]):
        paragraphs = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
        summary = next((p for p in paragraphs if not p.lstrip().startswith("*")), "")
        bullets = [clean(b, 300) for b in bullet_items(body, bullet=r"\*")]
        result.append(RemovedApi(resource=title.strip(), summary=clean(summary, 400), bullets=bullets))
    return result
