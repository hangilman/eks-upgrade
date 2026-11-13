"""OS 와 무관하게 텍스트 파일을 읽기 위한 유틸리티.

Windows 기본 인코딩(cp949)에 의존하지 않도록 항상 인코딩을 명시한다.
"""

from __future__ import annotations

from pathlib import Path


def read_user_text(path: str | Path) -> str:
    """사용자가 편집한 파일을 읽는다. UTF-8(BOM 포함)을 우선하고, 메모장 등에서 ANSI(cp949)로 저장한 경우도 허용."""
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949")
