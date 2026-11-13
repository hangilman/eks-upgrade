"""components.yaml 로드."""

from __future__ import annotations

from importlib import resources
import yaml

from .textio import read_user_text


def load_components(path: str | None) -> dict[str, dict]:
    if path:
        data = yaml.safe_load(read_user_text(path))
    else:
        data = yaml.safe_load(resources.files("eks_precheck").joinpath("data/components.yaml").read_text(encoding="utf-8"))
    comps = (data or {}).get("components") or {}
    if not isinstance(comps, dict):
        raise ValueError("components.yaml 의 'components' 는 매핑이어야 합니다")
    return {name: (spec or {}) for name, spec in comps.items()}


def select(components: dict[str, dict], names: str | None) -> dict[str, dict]:
    if not names:
        return components
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in wanted if n not in components]
    if unknown:
        raise ValueError(f"정의되지 않은 컴포넌트: {', '.join(unknown)} (사용 가능: {', '.join(components)})")
    return {n: components[n] for n in wanted}
