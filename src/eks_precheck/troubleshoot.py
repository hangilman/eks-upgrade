"""트러블슈팅 로드맵 데이터 (data/troubleshooting.yaml) 로드 / 검증."""

from __future__ import annotations

from importlib import resources

import yaml


def load() -> dict:
    data = yaml.safe_load(resources.files("eks_precheck").joinpath("data/troubleshooting.yaml").read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: dict) -> None:
    phases = data.get("phases") or []
    symptoms = data.get("symptoms") or []
    phase_ids = {p["id"] for p in phases}
    symptom_ids = [s["id"] for s in symptoms]
    if len(symptom_ids) != len(set(symptom_ids)):
        raise ValueError("troubleshooting.yaml: 증상 id 중복")
    for p in phases:
        for sid in p.get("watch", []):
            if sid not in symptom_ids:
                raise ValueError(f"troubleshooting.yaml: 단계 {p['id']} 의 watch 에 없는 증상 {sid}")
    for s in symptoms:
        if s.get("phase") not in phase_ids:
            raise ValueError(f"troubleshooting.yaml: 증상 {s['id']} 의 phase {s.get('phase')} 가 없음")
        if not s.get("causes"):
            raise ValueError(f"troubleshooting.yaml: 증상 {s['id']} 에 causes 가 없음")
