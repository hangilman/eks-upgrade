"""--cluster 모드: 실제 EKS 클러스터 상태를 read-only 로 조회.

필요 권한 (모두 읽기 전용):
  eks:DescribeCluster, eks:ListAddons, eks:DescribeAddon, eks:DescribeAddonVersions,
  eks:ListNodegroups, eks:DescribeNodegroup, eks:ListInsights, eks:DescribeInsight
  (+ self-managed 컴포넌트 버전 탐지 시 kubectl 로 deployments/daemonsets get/list)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from . import versions
from .models import AddonCompat, ClusterState, Insight, NodeGroup


class ClusterError(Exception):
    pass


def _eks_client(region: str | None, profile: str | None):
    try:
        import boto3
    except ImportError as e:
        raise ClusterError("boto3 가 필요합니다: pip install -e '.[cluster]'") from e
    session = boto3.Session(profile_name=profile, region_name=region)
    if not session.region_name:
        raise ClusterError("리전을 알 수 없습니다. --region 또는 AWS_REGION 을 지정하세요.")
    return session.client("eks"), session.region_name


def _paginate(client, op: str, key: str, **kwargs) -> list[Any]:
    out: list[Any] = []
    if client.can_paginate(op):
        for page in client.get_paginator(op).paginate(**kwargs):
            out += page.get(key, [])
        return out
    token = None
    while True:  # paginator 가 없는 botocore 버전 대비
        page = getattr(client, op)(**kwargs, **({"nextToken": token} if token else {}))
        out += page.get(key, [])
        token = page.get("nextToken")
        if not token:
            return out


def addon_compat(client, addon: str, current: str | None, minors: list[str]) -> tuple[AddonCompat, dict[str, str]]:
    """경로상 각 마이너 버전에서 현재 add-on 버전이 호환되는지, 기본(default) 버전은 무엇인지 조회."""
    compat = AddonCompat()
    defaults: dict[str, str] = {}
    for minor in minors:
        entries = _paginate(
            client, "describe_addon_versions", "addons", addonName=addon, kubernetesVersion=minor
        )
        available: list[str] = []
        default = None
        for entry in entries:
            for av in entry.get("addonVersions", []):
                for c in av.get("compatibilities", []):
                    if c.get("clusterVersion") == minor:
                        available.append(av["addonVersion"])
                        if c.get("defaultVersion"):
                            default = av["addonVersion"]
        latest = max(available, key=lambda v: versions.parse(v) or (0, 0, 0), default=None)
        compat.per_minor[minor] = {
            "current_compatible": (current in available) if current else None,
            "default": default,
            "latest": latest,
        }
        if default:
            defaults[minor] = default
    return compat, defaults


def detect_image_versions(components: dict[str, dict], kube_context: str | None) -> tuple[dict[str, str], str | None]:
    """kubectl 로 Deployment/DaemonSet 이미지 태그를 읽어 self-managed 컴포넌트 버전을 추정."""
    if not shutil.which("kubectl"):
        return {}, "kubectl 이 없어 self-managed 컴포넌트 버전 탐지를 건너뜁니다."
    cmd = ["kubectl", "get", "deployments,daemonsets", "-A", "-o", "json"]
    if kube_context:
        cmd += ["--context", kube_context]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return {}, f"kubectl 실행 실패: {e}"
    if out.returncode != 0:
        return {}, f"kubectl 실행 실패: {out.stderr.strip()[:200]}"
    return images_to_versions(json.loads(out.stdout), components), None


def images_to_versions(obj: dict, components: dict[str, dict]) -> dict[str, str]:
    images: list[str] = []
    for item in obj.get("items", []):
        for c in item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
            images.append(c.get("image", ""))
    found: dict[str, str] = {}
    for name, spec in components.items():
        match = spec.get("image_match")
        if not match:
            continue
        for image in images:
            if match in image:
                tag = image.split("@")[0].rsplit(":", 1)[-1]
                if versions.parse(tag):
                    found[name] = tag
                    break
    return found


def collect(
    cluster: str,
    region: str | None,
    profile: str | None,
    target_minor: str,
    components: dict[str, dict],
    kube_context: str | None = None,
) -> tuple[ClusterState, list[str]]:
    warnings: list[str] = []
    client, region = _eks_client(region, profile)
    try:
        info = client.describe_cluster(name=cluster)["cluster"]
    except Exception as e:  # botocore ClientError / NoCredentialsError 등
        raise ClusterError(f"describe-cluster 실패: {e}") from e

    state = ClusterState(
        name=cluster, region=region, version=info["version"], platform_version=info.get("platformVersion", "")
    )
    minors = versions.upgrade_path(state.version, target_minor) if state.version != target_minor else [target_minor]
    path_minors = [state.version, *minors] if state.version != target_minor else minors

    # Add-on
    for addon in _paginate(client, "list_addons", "addons", clusterName=cluster):
        state.addons[addon] = client.describe_addon(clusterName=cluster, addonName=addon)["addon"]["addonVersion"]
    for spec in components.values():
        addon = spec.get("eks_addon")
        if not addon:
            continue
        try:
            compat, defaults = addon_compat(client, addon, state.addons.get(addon), path_minors)
            state.addon_compat[addon] = compat
            if target_minor in defaults:
                state.addon_defaults[addon] = defaults[target_minor]
        except Exception as e:
            warnings.append(f"describe-addon-versions({addon}) 실패: {e}")

    # Node group
    for ng in _paginate(client, "list_nodegroups", "nodegroups", clusterName=cluster):
        d = client.describe_nodegroup(clusterName=cluster, nodegroupName=ng)["nodegroup"]
        state.nodegroups.append(
            NodeGroup(
                name=ng,
                version=d.get("version", ""),
                ami_type=d.get("amiType", ""),
                release_version=d.get("releaseVersion", ""),
                capacity_type=d.get("capacityType", ""),
            )
        )

    # Upgrade Insights
    try:
        for ins in _paginate(
            client,
            "list_insights",
            "insights",
            clusterName=cluster,
            filter={"categories": ["UPGRADE_READINESS"]},
        ):
            status = ins.get("insightStatus", {})
            insight = Insight(
                id=ins["id"],
                name=ins.get("name", ""),
                status=status.get("status", "UNKNOWN"),
                reason=status.get("reason", ""),
                kubernetes_version=ins.get("kubernetesVersion", ""),
            )
            if insight.status != "PASSING":
                detail = client.describe_insight(clusterName=cluster, id=insight.id)["insight"]
                insight.recommendation = detail.get("recommendation", "")
                insight.deprecations = detail.get("categorySpecificSummary", {}).get("deprecationDetails", [])
            state.insights.append(insight)
    except Exception as e:
        warnings.append(f"EKS Upgrade Insights 조회 실패: {e}")

    # self-managed 컴포넌트 (이미지 태그)
    image_versions, warn = detect_image_versions(components, kube_context)
    state.image_versions = image_versions
    if warn:
        warnings.append(warn)
    return state, warnings
