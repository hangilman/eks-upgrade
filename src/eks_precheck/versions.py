"""버전 문자열 파싱/비교 유틸리티."""

from __future__ import annotations

import re

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+](.+))?$")
_MINOR = re.compile(r"^v?(\d+)\.(\d+)(?:\.\d+)?$")

Version = tuple[int, int, int]


def parse(value: str | None) -> Version | None:
    """'v1.18.0', '1.18.0-eksbuild.1', '1.31' 등을 (major, minor, patch) 로 변환."""
    if not value:
        return None
    m = _SEMVER.match(value.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_prerelease(value: str) -> bool:
    """rc/alpha/beta 태그는 prerelease. EKS 의 '-eksbuild.N' 은 정식 빌드로 취급."""
    m = _SEMVER.match(value.strip())
    if not m or not m.group(4):
        return False
    return not m.group(4).startswith("eksbuild")


def fmt(v: Version | None) -> str:
    return "-" if v is None else f"v{v[0]}.{v[1]}.{v[2]}"


def parse_minor(value: str) -> tuple[int, int]:
    """'1.31' 또는 'v1.31.2' -> (1, 31)."""
    m = _MINOR.match(value.strip())
    if not m:
        raise ValueError(f"Kubernetes 버전 형식이 아닙니다: {value!r} (예: 1.31)")
    return int(m.group(1)), int(m.group(2))


def minor_str(v: tuple[int, int] | Version) -> str:
    return f"{v[0]}.{v[1]}"


def upgrade_path(current: str, target: str) -> list[str]:
    """컨트롤 플레인은 마이너 버전을 한 단계씩만 올릴 수 있으므로 거쳐야 하는 버전 목록을 반환.

    upgrade_path('1.29', '1.31') -> ['1.30', '1.31']
    """
    cur, tgt = parse_minor(current), parse_minor(target)
    if cur[0] != tgt[0]:
        raise ValueError("major 버전이 다른 업그레이드는 지원하지 않습니다")
    if tgt[1] <= cur[1]:
        raise ValueError(f"목표 버전({target})이 현재 버전({current})보다 높아야 합니다")
    return [f"{cur[0]}.{m}" for m in range(cur[1] + 1, tgt[1] + 1)]
