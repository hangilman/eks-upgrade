"""EKS 최적화 AMI 의 권장 이미지 ID 조회 (AWS 공개 SSM 파라미터).

경로 출처: Amazon EKS User Guide
  - Amazon Linux : /aws/service/eks/optimized-ami/<k8s>/<ami-type>/recommended/image_id
  - Bottlerocket : /aws/service/bottlerocket/aws-k8s-<k8s>[-nvidia]/<arch>/latest/image_id
  - Windows      : /aws/service/ami-windows-latest/Windows_Server-<release>-English-<option>-EKS_Optimized-<k8s>/image_id
AMI ID 는 리전마다 다르고, 조회 시점의 '권장(recommended/latest)' 이미지이므로 시간이 지나면 바뀐다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .awscli import AwsCliError, default_region, run_json

# EKS 노드그룹 amiType -> (SSM 기본 경로 템플릿, 조회할 하위 파라미터)
_AL = "/aws/service/eks/optimized-ami/{v}/{t}/recommended"
_BR = "/aws/service/bottlerocket/aws-k8s-{v}{flavor}/{arch}/latest"
_WIN = "/aws/service/ami-windows-latest/Windows_Server-{rel}-English-{opt}-EKS_Optimized-{v}"
AL_SUB = ["image_id", "release_version", "image_name"]
BR_SUB = ["image_id", "image_version"]

AMI_TYPES: dict[str, tuple[str, dict, list[str]]] = {
    "AL2023_x86_64_STANDARD": (_AL, {"t": "amazon-linux-2023/x86_64/standard"}, AL_SUB),
    "AL2023_ARM_64_STANDARD": (_AL, {"t": "amazon-linux-2023/arm64/standard"}, AL_SUB),
    "AL2023_x86_64_NVIDIA": (_AL, {"t": "amazon-linux-2023/x86_64/nvidia"}, AL_SUB),
    "AL2023_ARM_64_NVIDIA": (_AL, {"t": "amazon-linux-2023/arm64/nvidia"}, AL_SUB),
    "AL2023_x86_64_NEURON": (_AL, {"t": "amazon-linux-2023/x86_64/neuron"}, AL_SUB),
    "AL2_x86_64": (_AL, {"t": "amazon-linux-2"}, AL_SUB),
    "AL2_ARM_64": (_AL, {"t": "amazon-linux-2-arm64"}, AL_SUB),
    "AL2_x86_64_GPU": (_AL, {"t": "amazon-linux-2-gpu"}, AL_SUB),
    "BOTTLEROCKET_x86_64": (_BR, {"flavor": "", "arch": "x86_64"}, BR_SUB),
    "BOTTLEROCKET_ARM_64": (_BR, {"flavor": "", "arch": "arm64"}, BR_SUB),
    "BOTTLEROCKET_x86_64_NVIDIA": (_BR, {"flavor": "-nvidia", "arch": "x86_64"}, BR_SUB),
    "BOTTLEROCKET_ARM_64_NVIDIA": (_BR, {"flavor": "-nvidia", "arch": "arm64"}, BR_SUB),
    "WINDOWS_CORE_2019_x86_64": (_WIN, {"rel": "2019", "opt": "Core"}, ["image_id"]),
    "WINDOWS_FULL_2019_x86_64": (_WIN, {"rel": "2019", "opt": "Full"}, ["image_id"]),
    "WINDOWS_CORE_2022_x86_64": (_WIN, {"rel": "2022", "opt": "Core"}, ["image_id"]),
    "WINDOWS_FULL_2022_x86_64": (_WIN, {"rel": "2022", "opt": "Full"}, ["image_id"]),
}


@dataclass
class AmiInfo:
    ami_type: str
    minor: str
    region: str = ""
    image_id: str = ""
    release_version: str = ""
    image_name: str = ""
    parameter: str = ""
    queried_at: str = ""
    error: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def command(self) -> str:
        region = f" --region {self.region}" if self.region else ""
        return f"aws ssm get-parameter --name {self.parameter}/image_id --query Parameter.Value --output text{region}"


def parameter_base(ami_type: str, minor: str) -> tuple[str, list[str]] | None:
    entry = AMI_TYPES.get(ami_type)
    if not entry:
        return None
    template, args, subs = entry
    return template.format(v=minor, **args), subs


class AmiLookup:
    """같은 (타입, 버전) 은 한 번만 조회하도록 캐시."""

    def __init__(self, profile: str | None = None, region: str | None = None, enabled: bool = True):
        self.profile = profile
        self.region = region
        self.enabled = enabled
        self._cache: dict[tuple[str, str], AmiInfo] = {}
        self._region_resolved = False

    def _region(self) -> str | None:
        if not self._region_resolved:
            self.region = self.region or default_region(self.profile)
            self._region_resolved = True
        return self.region

    def get(self, ami_type: str, minor: str) -> AmiInfo:
        key = (ami_type, minor)
        if key in self._cache:
            return self._cache[key]
        info = AmiInfo(ami_type=ami_type, minor=minor)
        base = parameter_base(ami_type, minor)
        if base is None:
            info.error = "EKS 최적화 AMI 타입이 아니어서 조회하지 않음 (CUSTOM / 미지정)"
            self._cache[key] = info
            return info
        info.parameter, subs = base
        if not self.enabled:
            info.error = "AWS 조회 비활성화됨"
            self._cache[key] = info
            return info
        info.region = self._region() or ""
        try:
            data = run_json(
                ["ssm", "get-parameters", "--names", *[f"{info.parameter}/{s}" for s in subs]],
                self.profile, info.region or None,
            )
        except AwsCliError as e:
            info.error = str(e)
            self._cache[key] = info
            return info
        values = {p["Name"].rsplit("/", 1)[-1]: p.get("Value", "") for p in (data or {}).get("Parameters", [])}
        info.image_id = values.get("image_id", "")
        info.release_version = values.get("release_version") or values.get("image_version", "")
        info.image_name = values.get("image_name", "")
        info.queried_at = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        if not info.image_id:
            info.extra["missing"] = True
            info.error = (f"Kubernetes {minor} 용 {ami_type} AMI 가 없습니다 "
                          "(해당 버전에서 제공되지 않는 AMI 타입이거나 아직 출시 전).")
        self._cache[key] = info
        return info
