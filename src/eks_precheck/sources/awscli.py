"""AWS CLI 호출 공통 유틸리티 (read-only 명령만 사용)."""

from __future__ import annotations

import json
import shutil
import subprocess


class AwsCliError(Exception):
    pass


def run_json(args: list[str], profile: str | None = None, region: str | None = None, timeout: int = 30):
    aws = shutil.which("aws")
    if not aws:
        raise AwsCliError("AWS CLI 가 설치되어 있지 않음")
    cmd = [aws, *args, "--output", "json"]
    if profile:
        cmd += ["--profile", profile]
    if region:
        cmd += ["--region", region]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise AwsCliError(f"AWS CLI 실행 실패: {e}") from e
    if out.returncode != 0:
        msg = [ln for ln in (out.stderr or out.stdout).strip().splitlines() if ln.strip()]
        raise AwsCliError("AWS CLI 오류: " + (msg[-1] if msg else f"exit {out.returncode}"))
    try:
        return json.loads(out.stdout or "null")
    except ValueError as e:
        raise AwsCliError("AWS CLI 응답을 해석하지 못함") from e


def default_region(profile: str | None = None) -> str | None:
    aws = shutil.which("aws")
    if not aws:
        return None
    cmd = [aws, "configure", "get", "region"] + (["--profile", profile] if profile else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None
