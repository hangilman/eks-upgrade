from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text()


class FakeHttp:
    """URL -> 응답 매핑으로 동작하는 HttpClient 대체."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, params=None, headers=None, as_json=False):
        from eks_precheck.http import FetchError

        self.calls.append((url, params))
        for key, value in self.routes.items():
            if url == key or (url.startswith(key) and key.endswith("/")):
                if isinstance(value, Exception):
                    raise value
                return value(params) if callable(value) else value
        raise FetchError(f"{url}: HTTP 404")


@pytest.fixture
def fake_http():
    return FakeHttp
