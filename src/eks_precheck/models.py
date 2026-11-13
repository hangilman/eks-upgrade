"""리포트 생성에 쓰이는 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field

# severity
CRITICAL = "critical"  # 🔴 반드시 조치/확인
REVIEW = "review"      # 🟡 검토 필요
SECURITY = "security"  # 🔒 보안 수정
INFO = "info"          # 리포트에는 건수만 표시


@dataclass
class Finding:
    severity: str
    text: str
    source: str = ""  # 예: 릴리스 태그
    url: str = ""


@dataclass
class Issue:
    number: int
    title: str
    url: str
    updated_at: str
    labels: list[str] = field(default_factory=list)


@dataclass
class RemovedApi:
    resource: str
    summary: str
    bullets: list[str] = field(default_factory=list)


@dataclass
class VersionReport:
    """Kubernetes 마이너 버전 1단계에 대한 변경사항."""

    minor: str
    removed_apis: list[RemovedApi] = field(default_factory=list)
    eks_important: list[str] = field(default_factory=list)
    eks_subsections: list[tuple[str, str]] = field(default_factory=list)
    eks_notes: list[str] = field(default_factory=list)
    urgent_notes: list[str] = field(default_factory=list)
    deprecations: list[str] = field(default_factory=list)
    api_changes: list[str] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)


@dataclass
class AddonCompat:
    """EKS managed add-on 의 버전별 호환성 (cluster 모드)."""

    per_minor: dict[str, dict] = field(default_factory=dict)
    # per_minor['1.31'] = {'current_compatible': bool, 'default': 'v1.19.0-eksbuild.1', 'latest': '...'}


@dataclass
class ComponentReport:
    name: str
    repo: str | None
    current: str | None = None
    current_source: str = ""  # 'cluster(add-on)', 'cluster(image)', 'cli', ''
    target: str | None = None
    target_source: str = ""
    release_tags: list[tuple[str, str]] = field(default_factory=list)  # (tag, url)
    findings: list[Finding] = field(default_factory=list)
    info_count: int = 0
    issues: list[Issue] = field(default_factory=list)
    compat: AddonCompat | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class NodeGroup:
    name: str
    version: str
    ami_type: str
    release_version: str = ""
    capacity_type: str = ""


@dataclass
class Insight:
    id: str
    name: str
    status: str
    reason: str
    kubernetes_version: str
    recommendation: str = ""
    deprecations: list[dict] = field(default_factory=list)


@dataclass
class ClusterState:
    name: str
    region: str
    version: str
    platform_version: str = ""
    addons: dict[str, str] = field(default_factory=dict)
    nodegroups: list[NodeGroup] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)
    image_versions: dict[str, str] = field(default_factory=dict)
    addon_compat: dict[str, AddonCompat] = field(default_factory=dict)
    addon_defaults: dict[str, str] = field(default_factory=dict)  # 목표 버전 기본 add-on 버전


@dataclass
class Report:
    from_minor: str
    to_minor: str
    path: list[str]
    generated_at: str
    cluster: ClusterState | None = None
    cluster_findings: list[Finding] = field(default_factory=list)
    versions: list[VersionReport] = field(default_factory=list)
    components: list[ComponentReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
