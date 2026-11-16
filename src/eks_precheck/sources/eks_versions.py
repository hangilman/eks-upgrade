"""EKS 가 지원하는 Kubernetes 버전 확인.

신뢰도 순서:
  1) AWS API `aws eks describe-cluster-versions` (AWS CLI 자격증명이 있을 때, read-only)
  2) AWS 문서 사이트 (docs.aws.amazon.com) 의 버전 페이지
  3) GitHub 문서 원본(awsdocs/amazon-eks-user-guide) — 갱신이 늦을 수 있어 지원 여부 판단에는 쓰지 않음
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from ..http import FetchError, HttpClient
from .eks_docs import DOCS

SOURCE_API = "AWS API (describe-cluster-versions)"
SOURCE_DOCS = "AWS 문서 사이트"

STANDARD = "STANDARD_SUPPORT"
EXTENDED = "EXTENDED_SUPPORT"
UNSUPPORTED = "UNSUPPORTED"

MIRROR_COMMITS_API = "https://api.github.com/repos/awsdocs/amazon-eks-user-guide/commits"


@dataclass
class SupportInfo:
    source: str = ""  # 비어 있으면 공식 출처로 확인하지 못한 것
    versions: dict[str, str] = field(default_factory=dict)  # '1.37' -> STANDARD_SUPPORT ...
    details: dict[str, dict] = field(default_factory=dict)  # '1.37' -> {'releaseDate': ..., ...}
    errors: list[str] = field(default_factory=list)


def _normalize(status: str | None) -> str:
    s = (status or "").upper().replace("-", "_")
    return s if s in (STANDARD, EXTENDED, UNSUPPORTED) else STANDARD


def from_aws_cli(profile: str | None = None, region: str | None = None, timeout: int = 30) -> tuple[SupportInfo | None, str]:
    aws = shutil.which("aws")
    if not aws:
        return None, "AWS CLI 가 설치되어 있지 않음"
    cmd = [aws, "eks", "describe-cluster-versions", "--output", "json"]
    if profile:
        cmd += ["--profile", profile]
    if region:
        cmd += ["--region", region]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=timeout, env={**os.environ, "AWS_PAGER": ""})
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"AWS CLI 실행 실패: {e}"
    if out.returncode != 0:
        msg = (out.stderr or out.stdout).strip().splitlines()
        return None, "AWS CLI 오류: " + (msg[-1] if msg else f"exit {out.returncode}")
    try:
        data = json.loads(out.stdout)
    except ValueError:
        return None, "AWS CLI 응답을 해석하지 못함"
    info = SupportInfo(source=SOURCE_API)
    for v in data.get("clusterVersions", []):
        minor = str(v.get("clusterVersion", ""))
        if not re.fullmatch(r"\d+\.\d+", minor):
            continue
        info.versions[minor] = _normalize(v.get("versionStatus") or v.get("status"))
        info.details[minor] = {
            k: str(v[k])[:10]
            for k in ("releaseDate", "endOfStandardSupportDate", "endOfExtendedSupportDate")
            if v.get(k)
        }
    if not info.versions:
        return None, "AWS CLI 응답에 버전 정보가 없음"
    return info, ""


_ANCHOR = re.compile(r'id="kubernetes-(\d+)-(\d+)"')


def from_live_docs(http: HttpClient) -> tuple[SupportInfo | None, str]:
    info = SupportInfo(source=SOURCE_DOCS)
    for kind, status in (("standard", STANDARD), ("extended", EXTENDED)):
        try:
            html = http.get(DOCS[kind][1])
        except FetchError as e:
            reason = "프록시/네트워크 차단" if "proxy" in str(e).lower() or "connect" in str(e).lower() else str(e)[-80:]
            return None, f"AWS 문서 사이트 접근 실패 ({reason})"
        for a, b in _ANCHOR.findall(html):
            info.versions.setdefault(f"{a}.{b}", status)
    if not info.versions:
        return None, "AWS 문서 사이트에서 버전 목록을 읽지 못함 (페이지 형식 변경 가능)"
    return info, ""


def resolve(http: HttpClient, use_aws: bool, profile: str | None, region: str | None, log) -> SupportInfo:
    errors = []
    if use_aws:
        log("  - EKS 지원 버전 확인: AWS CLI (describe-cluster-versions)")
        info, err = from_aws_cli(profile, region)
        if info:
            return info
        errors.append(err)
    log("  - EKS 지원 버전 확인: AWS 문서 사이트")
    info, err = from_live_docs(http)
    if info:
        info.errors = errors
        return info
    errors.append(err)
    return SupportInfo(errors=errors)


def mirror_last_updated(http: HttpClient) -> str | None:
    """GitHub 문서 원본의 버전 문서 마지막 커밋 날짜 (YYYY-MM-DD)."""
    try:
        data = http.get(
            MIRROR_COMMITS_API, params={"path": "latest/ug/versioning", "per_page": 1}, as_json=True
        )
        return data[0]["commit"]["committer"]["date"][:10]
    except (FetchError, LookupError, TypeError):
        return None
