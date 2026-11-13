"""사용자 입력 파일(env.yaml) 로드/검증."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from . import versions
from .models import NodeGroup
from .textio import read_user_text


class InputError(ValueError):
    pass


INSTALL_EKS = "eks-addon"
INSTALL_HELM = "helm"


@dataclass
class EnvInput:
    current: str
    target: str
    components: dict[str, dict] = field(default_factory=dict)  # 분석 대상만
    current_versions: dict[str, str] = field(default_factory=dict)
    target_versions: dict[str, str] = field(default_factory=dict)
    nodegroups: list[NodeGroup] = field(default_factory=list)
    aws_profile: str | None = None
    aws_region: str | None = None


def template_text() -> str:
    return resources.files("eks_precheck").joinpath("data/env-template.yaml").read_text(encoding="utf-8")


def _version(value, where: str) -> str:
    if isinstance(value, float):
        raise InputError(f"{where}: 버전 {value!r} 을 따옴표로 감싸 주세요 (예: \"1.30\"). 따옴표가 없으면 1.30 이 1.3 으로 읽힙니다.")
    if value is None or str(value).strip() == "":
        raise InputError(f"{where}: 값이 비어 있습니다.")
    return str(value).strip()


def _minor(value, where: str) -> str:
    v = _version(value, where)
    try:
        return versions.minor_str(versions.parse_minor(v))
    except ValueError as e:
        raise InputError(f"{where}: {e}") from e


def load(path: str | Path, known: dict[str, dict]) -> EnvInput:
    return from_dict(load_raw(path), known)


def load_raw(path: str | Path) -> dict:
    """입력 파일을 검증 없이 dict 로 읽는다 (웹 UI 의 초기값 채우기용)."""
    try:
        data = yaml.safe_load(read_user_text(path)) or {}
    except FileNotFoundError as e:
        raise InputError(f"입력 파일이 없습니다: {path}  (템플릿 생성: eks-precheck init)") from e
    except UnicodeDecodeError as e:
        raise InputError(f"{path}: 파일 인코딩을 읽을 수 없습니다. UTF-8 로 저장해 주세요.") from e
    except yaml.YAMLError as e:
        raise InputError(f"YAML 형식 오류: {e}") from e
    if not isinstance(data, dict):
        raise InputError("입력 파일 최상위는 cluster / addons / nodegroups 항목이어야 합니다.")
    return data


def from_dict(data: dict, known: dict[str, dict]) -> EnvInput:
    """dict(입력 파일 또는 웹 UI 입력)를 검증해 EnvInput 으로 변환."""
    cluster = data.get("cluster") or {}
    env = EnvInput(
        current=_minor(cluster.get("current"), "cluster.current"),
        target=_minor(cluster.get("target"), "cluster.target"),
    )
    try:
        versions.upgrade_path(env.current, env.target)
    except ValueError as e:
        raise InputError(f"cluster: {e}") from e

    for name, value in (data.get("addons") or {}).items():
        where = f"addons.{name}"
        spec = dict(known.get(name, {}))
        install = None
        if isinstance(value, dict):
            current, target, install = value.get("current"), value.get("target"), value.get("install")
            spec.update({k: v for k, v in value.items()
                         if k not in ("current", "target", "install") and v not in (None, "")})
        else:
            current, target = value, None
        if install not in (None, "", INSTALL_EKS, INSTALL_HELM):
            raise InputError(f"{where}.install: {INSTALL_EKS} 또는 {INSTALL_HELM} 중 하나여야 합니다.")
        if install == INSTALL_EKS and not spec.get("eks_addon"):
            raise InputError(f"{where}: EKS 관리형 add-on 으로 제공되지 않는 컴포넌트입니다. install: {INSTALL_HELM} 으로 지정하세요.")
        spec["install"] = install or (INSTALL_EKS if spec.get("eks_addon") else INSTALL_HELM)
        if spec["install"] == INSTALL_HELM:
            spec.pop("eks_addon", None)  # Helm 설치면 EKS add-on 호환성 조회 대상이 아님
        if not spec.get("repo") and not spec.get("eks_addon") and name not in known:
            raise InputError(
                f"{where}: 알 수 없는 컴포넌트입니다. repo: owner/name 을 함께 적어 주세요. "
                f"(기본 지원: {', '.join(known)})"
            )
        env.components[name] = spec
        env.current_versions[name] = _version(current, f"{where}.current" if isinstance(value, dict) else where)
        if target not in (None, ""):
            env.target_versions[name] = _version(target, f"{where}.target")

    aws = data.get("aws") or {}
    if not isinstance(aws, dict):
        raise InputError("aws: profile / region 형식으로 적어 주세요.")
    env.aws_profile = str(aws["profile"]) if aws.get("profile") else None
    env.aws_region = str(aws["region"]) if aws.get("region") else None

    for i, ng in enumerate(data.get("nodegroups") or []):
        where = f"nodegroups[{i}]"
        if not isinstance(ng, dict):
            raise InputError(f"{where}: name / version / ami_type 형식으로 적어 주세요.")
        env.nodegroups.append(
            NodeGroup(
                name=str(ng.get("name") or f"nodegroup-{i + 1}"),
                version=_minor(ng.get("version"), f"{where}.version"),
                ami_type=str(ng.get("ami_type") or ""),
                ami_id=str(ng.get("ami_id") or "").strip(),
            )
        )
    return env
