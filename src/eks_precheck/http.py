"""파일 캐시가 있는 HTTP 클라이언트."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

def _default_cache_dir() -> Path:
    if os.name == "nt":  # Windows: %LOCALAPPDATA%\eks-precheck\cache
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "eks-precheck" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "eks-precheck"


DEFAULT_CACHE_DIR = _default_cache_dir()
DEFAULT_TTL = 6 * 3600


class FetchError(Exception):
    pass


class RateLimited(FetchError):
    pass


class HttpClient:
    def __init__(
        self,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        ttl: int = DEFAULT_TTL,
        github_token: str | None = None,
        timeout: int = 30,
    ):
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.github_token = github_token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "eks-precheck"

    def _cache_file(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def get(self, url: str, params: dict | None = None, headers: dict | None = None, as_json: bool = False) -> Any:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        cache_file = self._cache_file(key)
        if cache_file and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if time.time() - cached["ts"] < self.ttl:
                    return cached["data"]
            except (ValueError, KeyError, OSError):
                pass

        hdrs = dict(headers or {})
        if self.github_token and url.startswith("https://api.github.com"):
            hdrs["Authorization"] = f"Bearer {self.github_token}"
        try:
            resp = self.session.get(url, params=params, headers=hdrs, timeout=self.timeout)
        except requests.RequestException as e:
            raise FetchError(f"{url}: {e}") from e

        if resp.status_code == 429 or (
            resp.status_code == 403
            and (resp.headers.get("X-RateLimit-Remaining") == "0" or "rate limit" in resp.text.lower())
        ):
            reset = resp.headers.get("X-RateLimit-Reset")
            when = time.strftime("%H:%M:%S", time.localtime(int(reset))) if reset else "잠시 후"
            raise RateLimited(f"GitHub API rate limit 초과 ({when} 이후 재시도 가능). GITHUB_TOKEN 설정을 권장합니다.")
        if resp.status_code >= 400:
            raise FetchError(f"{url}: HTTP {resp.status_code}")

        data = resp.json() if as_json else resp.text
        if cache_file:
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps({"ts": time.time(), "data": data}), encoding="utf-8")
            except OSError:
                pass
        return data
