"""GitHub Release / Issue 수집."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from .. import versions
from ..http import HttpClient
from ..models import Issue

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
DEFAULT_TAG_PATTERN = r"^v?\d+\.\d+\.\d+$"


@dataclass
class Release:
    tag: str
    name: str
    body: str
    url: str
    published_at: str
    prerelease: bool
    draft: bool


def resolve_token() -> str | None:
    """GITHUB_TOKEN / GH_TOKEN 환경변수, 없으면 `gh auth token` 결과를 사용."""
    for env in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(env):
            return os.environ[env]
    if shutil.which("gh"):
        try:
            out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


class GitHub:
    def __init__(self, http: HttpClient):
        self.http = http

    def releases(self, repo: str, max_pages: int = 3) -> list[Release]:
        out: list[Release] = []
        for page in range(1, max_pages + 1):
            data = self.http.get(
                f"{API}/repos/{repo}/releases",
                params={"per_page": 100, "page": page},
                headers=HEADERS,
                as_json=True,
            )
            out += [
                Release(
                    tag=r.get("tag_name", ""),
                    name=r.get("name") or "",
                    body=r.get("body") or "",
                    url=r.get("html_url", ""),
                    published_at=r.get("published_at") or "",
                    prerelease=bool(r.get("prerelease")),
                    draft=bool(r.get("draft")),
                )
                for r in data
            ]
            if len(data) < 100:
                break
        return out

    def search_issues(self, query: str, limit: int = 5) -> list[Issue]:
        data = self.http.get(
            f"{API}/search/issues",
            params={"q": query, "per_page": limit, "sort": "updated", "order": "desc"},
            headers=HEADERS,
            as_json=True,
        )
        return [
            Issue(
                number=i["number"],
                title=i.get("title", ""),
                url=i.get("html_url", ""),
                updated_at=(i.get("updated_at") or "")[:10],
                labels=[label.get("name", "") for label in i.get("labels", [])],
            )
            for i in data.get("items", [])
            if "pull_request" not in i
        ]


def versioned(
    releases: list[Release], tag_pattern: str = DEFAULT_TAG_PATTERN, tag_prefix: str = ""
) -> list[tuple[versions.Version, Release]]:
    """정식 릴리스만 (버전, 릴리스) 로 변환해 버전 오름차순으로 반환.

    tag_prefix 는 'controller-v1.11.2', 'cluster-autoscaler-1.31.0' 처럼 접두어가 붙은 태그용이다.
    """
    pattern = re.compile(tag_pattern)
    out = []
    for r in releases:
        tag = r.tag
        if tag_prefix:
            if not tag.startswith(tag_prefix):
                continue
            tag = tag[len(tag_prefix):]
        if r.draft or r.prerelease or not pattern.match(tag) or versions.is_prerelease(tag):
            continue
        v = versions.parse(tag)
        if v:
            out.append((v, r))
    out.sort(key=lambda x: x[0])
    return out


def select_releases(
    releases: list[Release],
    current: str | None,
    target: str | None,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    lookback: int = 5,
    tag_prefix: str = "",
) -> list[Release]:
    """current(미포함) ~ target(포함) 사이의 정식 릴리스를 버전 오름차순으로 반환.

    current 를 모르면 target 이하의 최근 `lookback` 개를 반환한다.
    """
    cur, tgt = versions.parse(current), versions.parse(target)
    result = [r for v, r in versioned(releases, tag_pattern, tag_prefix) if not (tgt and v > tgt) and not (cur and v <= cur)]
    return result if cur else result[-lookback:]


def latest_version(
    releases: list[Release], tag_pattern: str = DEFAULT_TAG_PATTERN, tag_prefix: str = "", minor: tuple[int, int] | None = None
) -> str | None:
    """최신 정식 릴리스 버전. minor 를 주면 해당 major.minor 안에서의 최신 버전."""
    vs = [v for v, _ in versioned(releases, tag_pattern, tag_prefix) if minor is None or v[:2] == minor]
    return versions.fmt(vs[-1]) if vs else None
