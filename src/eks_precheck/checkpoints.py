"""리포트 항목 본문 → '어디를 점검하면 되는지' 안내.

버전별 사실을 담지 않고, 원문에 특정 키워드가 나오면 확인할 위치와 명령을 연결하는 대응표다.
명령은 Windows(PowerShell) / Linux 양쪽에서 그대로 실행되는 형태로만 쓴다 (grep 등 파이프 사용 안 함).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Checkpoint:
    key: str
    title: str
    commands: tuple[str, ...] = ()


_RULES: list[tuple[re.Pattern, Checkpoint]] = [
    (re.compile(r"no longer served|stopped serving|API version .{0,80}removed|removed in version|제거되는 API", re.I),
     Checkpoint("removed-api", "제거되는 API 사용 여부 (클러스터 + 매니페스트 / Helm chart)", (
         "aws eks list-insights --cluster-name <클러스터> --filter categories=UPGRADE_READINESS",
         "pluto detect-helm -o wide",
     ))),
    (re.compile(r"cgroups? ?v1|failCgroupV1", re.I),
     Checkpoint("cgroup", "노드 OS 의 cgroup 버전 (AL2023 / Bottlerocket 은 v2, AL2 는 v1)", (
         "kubectl get nodes -o custom-columns=NAME:.metadata.name,OS:.status.nodeInfo.osImage,KERNEL:.status.nodeInfo.kernelVersion",
     ))),
    (re.compile(r"containerd", re.I),
     Checkpoint("containerd", "노드 container runtime(containerd) 버전", (
         "kubectl get nodes -o custom-columns=NAME:.metadata.name,RUNTIME:.status.nodeInfo.containerRuntimeVersion",
     ))),
    (re.compile(r"Amazon Linux 2(?!0)|\bAL2\b(?!0)", re.I),
     Checkpoint("al2", "Amazon Linux 2 AMI 를 쓰는 노드그룹 / Launch Template", (
         "kubectl get nodes -o custom-columns=NAME:.metadata.name,OS:.status.nodeInfo.osImage",
         "aws eks describe-nodegroup --cluster-name <클러스터> --nodegroup-name <노드그룹> --query nodegroup.amiType",
     ))),
    (re.compile(r"ingress[- ]?nginx", re.I),
     Checkpoint("ingress-nginx", "Ingress NGINX 사용 여부와 대체(Gateway API 등) 계획", (
         "kubectl get ingressclass",
     ))),
    (re.compile(r"kubelet .{0,40}(?:flag|configuration|config)|--[a-z][a-z-]+[` ]+(?:flag|was removed)|extraArgs", re.I),
     Checkpoint("kubelet-flags", "Launch Template user data / nodeadm 설정에 제거·변경된 kubelet 플래그가 있는지", (
         "aws ec2 describe-launch-template-versions --launch-template-id <lt-id> --versions '$Latest' --query LaunchTemplateVersions[0].LaunchTemplateData.UserData --output text",
     ))),
    (re.compile(r"\bipvs\b|nftables|iptables mode|kube-proxy mode", re.I),
     Checkpoint("kube-proxy-mode", "kube-proxy 동작 모드 (iptables / ipvs / nftables)", (
         "kubectl -n kube-system get configmap kube-proxy-config -o yaml",
     ))),
    (re.compile(r"anonymous|system:unauthenticated", re.I),
     Checkpoint("anonymous", "system:anonymous / system:unauthenticated 에 권한을 준 RBAC 바인딩", (
         "kubectl get clusterrolebindings -o wide",
     ))),
    (re.compile(r"selinux", re.I),
     Checkpoint("selinux", "SELinux enforcing 노드에서 쓰는 Pod 의 seLinuxChangePolicy / 볼륨 라벨", ())),
    (re.compile(r"\bEndpoints API\b|v1 Endpoints|Endpoints .{0,20}deprecat", re.I),
     Checkpoint("endpoints", "Endpoints API 를 직접 쓰는 컨트롤러·스크립트 (EndpointSlice 로 전환)", (
         "aws eks list-insights --cluster-name <클러스터> --filter categories=UPGRADE_READINESS",
     ))),
    (re.compile(r"scheduler plugin|custom (?:scheduler )?plugin|QueueingHint", re.I),
     Checkpoint("scheduler", "커스텀 스케줄러 / 스케줄러 플러그인 사용 여부", (
         "kubectl get pods -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,SCHEDULER:.spec.schedulerName",
     ))),
    (re.compile(r"volume plugin|in-tree|CSI driver|StorageClass", re.I),
     Checkpoint("storage", "StorageClass provisioner 와 PV 드라이버 (in-tree 사용 여부, CSI 드라이버 버전)", (
         "kubectl get storageclass",
         "kubectl get pv -o custom-columns=NAME:.metadata.name,CSI:.spec.csi.driver,CLASS:.spec.storageClassName",
     ))),
    (re.compile(r"Dynamic Resource Allocation|\bDRA\b", re.I),
     Checkpoint("dra", "GPU 등 Dynamic Resource Allocation(DRA) API 를 쓰는 workload", (
         "kubectl api-resources --api-group=resource.k8s.io",
     ))),
    (re.compile(r"PodSecurityPolicy|Pod Security", re.I),
     Checkpoint("pod-security", "네임스페이스의 Pod Security Admission 라벨", (
         "kubectl get namespaces --show-labels",
     ))),
    (re.compile(r"\bWindows\b"),
     Checkpoint("windows", "Windows 노드그룹의 AMI / 지원 버전", ())),
    (re.compile(r"feature[- ]gate", re.I),
     Checkpoint("feature-gate", "feature gate 변경: 컨트롤 플레인은 EKS 가 관리하므로, kubelet 설정 등 직접 지정한 곳만 확인", ())),
    (re.compile(r"NodePool|EC2NodeClass|\bProvisioner\b", re.I),
     Checkpoint("karpenter-api", "Karpenter NodePool / EC2NodeClass 리소스의 API 버전과 필드", (
         "kubectl get nodepools,ec2nodeclasses",
     ))),
    (re.compile(r"IAM (?:policy|permission|role)|\biam:[A-Z]|\bec2:[A-Z]|\belasticloadbalancing:[A-Z]", re.I),
     Checkpoint("iam", "컨트롤러 IAM 역할 정책 업데이트 필요 여부 (IRSA / Pod Identity)", (
         "kubectl get serviceaccounts -A -o 'custom-columns=NS:.metadata.namespace,NAME:.metadata.name,ROLE:.metadata.annotations.eks\\.amazonaws\\.com/role-arn'",
         "aws eks list-pod-identity-associations --cluster-name <클러스터>",
     ))),
    (re.compile(r"\bCRDs?\b|CustomResourceDefinition", re.I),
     Checkpoint("crd", "CRD 업그레이드 (Helm 은 crds/ 를 업그레이드하지 않으므로 수동 적용이 필요할 수 있음)", (
         "kubectl get crd",
     ))),
    (re.compile(r"(?:flag|argument|option|parameter|value|setting)s?\b.{0,30}\b(?:removed|renamed|deprecated)"
                r"|(?:removed|renamed|deprecated)\b.{0,30}\b(?:flag|argument|option|parameter|setting)", re.I),
     Checkpoint("options", "Helm values / 컨테이너 인자에서 제거·변경된 옵션을 쓰는지", (
         "helm get values <릴리스> -n <네임스페이스>",
     ))),
    (re.compile(r"webhook", re.I),
     Checkpoint("webhook", "Admission webhook 동작과 인증서 (실패 시 리소스 생성이 막힘)", (
         "kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations",
     ))),
    (re.compile(r"minimum (?:supported )?(?:kubernetes|k8s|eks)|requires? (?:kubernetes|k8s|eks)|kubernetes (?:version )?support", re.I),
     Checkpoint("k8s-compat", "컴포넌트가 업그레이드 경로의 각 Kubernetes 버전을 지원하는지 (호환 매트릭스)", ())),
    (re.compile(r"\bCVE-\d{4}-\d+|\bGHSA-", re.I),
     Checkpoint("cve", "보안 수정 포함: 해당 버전 이상으로 올리는 것을 권장", ())),
]


# 어디에나 걸리기 쉬운 범용 규칙: 🔴 항목에서 나올 때만 안내
_GENERIC = {"feature-gate", "options"}


def match(texts: list[str], limit: int | None = None, generic: bool = True) -> list[Checkpoint]:
    """텍스트 목록에서 해당하는 점검 포인트를 규칙 순서대로 (중복 없이) 반환."""
    joined = "\n".join(texts)
    found = [cp for pattern, cp in _RULES if (generic or cp.key not in _GENERIC) and pattern.search(joined)]
    return found[:limit] if limit else found


def prioritized(critical: list[str], review: list[str], limit: int | None = None) -> list[Checkpoint]:
    """🔴 항목에서 나온 점검 포인트를 먼저, 🟡 항목은 범용 규칙을 빼고 뒤에."""
    out: list[Checkpoint] = []
    for cp in match(critical) + match(review, generic=False):
        if cp not in out:
            out.append(cp)
    return out[:limit] if limit else out


def render(points: list[Checkpoint]) -> list[str]:
    """Markdown bullet 목록. 명령은 inline code 로."""
    out = []
    for p in points:
        cmds = " · ".join(f"`{c}`" for c in p.commands)
        out.append(f"- **{p.title}**" + (f" — {cmds}" if cmds else ""))
    return out
