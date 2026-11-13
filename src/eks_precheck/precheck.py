"""수집 → 분석 → Report 모델 생성."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from . import versions
from .classify import classify_release
from .http import FetchError, HttpClient, RateLimited
from .models import CRITICAL, INFO, REVIEW, ClusterState, ComponentReport, Finding, NodeGroup, Report, VersionReport
from .sources import eks_docs, eks_versions, k8s
from .sources.eks_versions import SupportInfo
from .sources.github import DEFAULT_TAG_PATTERN, GitHub, latest_version, select_releases

Log = Callable[[str], None]

KUBELET_MAX_SKEW = 3  # Kubernetes 1.28+ : kubelet 은 kube-apiserver 보다 최대 3 마이너 낮을 수 있음
AL2_LAST_MINOR = (1, 32)  # EKS 문서: 1.32 가 AL2 AMI 를 제공하는 마지막 버전


def build_version_reports(
    http: HttpClient, path: list[str], warnings: list[str], log: Log, support: SupportInfo | None = None
) -> list[VersionReport]:
    support = support or SupportInfo()
    try:
        guide = http.get(k8s.DEPRECATION_GUIDE_RAW)
    except FetchError as e:
        guide = ""
        warnings.append(f"Kubernetes Deprecation Guide 수집 실패: {e}")

    eks_texts: dict[str, str] = {}
    for kind, (raw, _web) in eks_docs.DOCS.items():
        try:
            eks_texts[kind] = http.get(raw)
        except FetchError as e:
            warnings.append(f"EKS 문서({kind}) 수집 실패: {e}")

    mirror_date = eks_versions.mirror_last_updated(http) if eks_texts else None
    reports = []
    for minor in path:
        log(f"  - Kubernetes {minor} 변경사항 수집")
        vr = VersionReport(minor=minor)
        vr.links["Kubernetes CHANGELOG"] = k8s.CHANGELOG_WEB.format(minor=minor)
        vr.links["Deprecation Guide"] = k8s.DEPRECATION_GUIDE_WEB
        if guide:
            vr.removed_apis = k8s.removed_apis(guide, minor)

        vr.links["EKS 릴리스 일정"] = eks_docs.RELEASE_CALENDAR
        vr.links["EKS 릴리스 노트 (AWS 문서)"] = eks_docs.DOCS["standard"][1]
        for kind, text in eks_texts.items():
            sec = eks_docs.find_section(text, minor)
            if sec:
                notes = eks_docs.parse_section(sec)
                vr.eks_important, vr.eks_notes, vr.eks_subsections = notes.important, notes.notes, notes.subsections
                vr.links["EKS 릴리스 노트 (AWS 문서)"] = eks_docs.DOCS[kind][1] + f"#kubernetes-{minor.replace('.', '-')}"
                vr.eks_status = kind
                break
        else:
            vr.eks_notes_missing = bool(eks_texts)
        _judge_eks_status(vr, support, eks_texts, mirror_date, warnings)

        try:
            changelog = http.get(k8s.CHANGELOG_RAW.format(minor=minor))
            sec = k8s.release_section(changelog, minor)
            if sec:
                vr.urgent_notes = k8s.urgent_notes(sec)
                vr.deprecations = k8s.kind_items(sec, "Deprecation")
                vr.api_changes = k8s.api_changes(sec)
            else:
                vr.upstream_released = False
                warnings.append(f"Kubernetes {minor} 는 업스트림에 아직 v{minor}.0 정식 릴리스가 없습니다 (출시 전 버전).")
        except FetchError as e:
            warnings.append(f"Kubernetes {minor} CHANGELOG 수집 실패: {e}")
        reports.append(vr)
    return reports


_STATUS_MAP = {eks_versions.STANDARD: "standard", eks_versions.EXTENDED: "extended", eks_versions.UNSUPPORTED: "ended"}


def _judge_eks_status(
    vr: VersionReport, support: SupportInfo, eks_texts: dict[str, str], mirror_date: str | None, warnings: list[str]
) -> None:
    """EKS 지원 상태 판단. 공식 출처(AWS API / AWS 문서 사이트)가 있을 때만 '미지원'으로 단정한다."""
    minor = versions.parse_minor(vr.minor)
    mirror_note = f"GitHub 문서 원본(마지막 갱신 {mirror_date})" if mirror_date else "GitHub 문서 원본"

    if support.source:
        vr.eks_status_source = support.source
        known = [versions.parse_minor(m) for m in support.versions]
        if vr.minor in support.versions:
            vr.eks_status = _STATUS_MAP[support.versions[vr.minor]]
            d = support.details.get(vr.minor, {})
            parts = [f"{label} {d[k]}" for k, label in (
                ("releaseDate", "EKS 출시"), ("endOfStandardSupportDate", "standard 지원 종료"),
                ("endOfExtendedSupportDate", "extended 지원 종료")) if k in d]
            if parts:
                vr.eks_status_note = " · ".join(parts)
        elif minor > max(known):
            vr.eks_status = "not_yet"
            vr.eks_status_note = (
                f"{support.source} 기준 Amazon EKS 는 아직 Kubernetes {vr.minor} 를 지원하지 않습니다 "
                f"(지원 최신 버전: {versions.minor_str(max(known))})."
            )
        else:
            vr.eks_status = "ended"
            vr.eks_status_note = f"{support.source} 기준 EKS 지원이 종료된 버전입니다."
        if vr.eks_notes_missing and vr.eks_status in ("standard", "extended"):
            vr.eks_status_note = (vr.eks_status_note + " / " if vr.eks_status_note else "") + (
                f"EKS 전용 변경사항은 {mirror_note}에 아직 없어 자동 추출하지 못했습니다. 위 'EKS 릴리스 노트' 링크에서 직접 확인하세요."
            )
        return

    # 공식 출처 확인 실패 → GitHub 문서 원본만으로는 '미지원'을 단정하지 않는다
    if vr.eks_status in ("standard", "extended"):
        vr.eks_status_source = mirror_note
        return
    mirror_known = [m for text in eks_texts.values() for m in eks_docs.available_minors(text)]
    if mirror_known and minor < min(mirror_known):
        vr.eks_status, vr.eks_status_source = "ended", mirror_note
        vr.eks_status_note = "EKS 문서에서 빠진 버전으로, EKS 지원이 종료된 것으로 보입니다."
        return
    vr.eks_status = "unverified"
    vr.eks_status_source = mirror_note
    vr.eks_status_note = (
        f"{mirror_note}에 Kubernetes {vr.minor} 내용이 없습니다. 문서 원본 갱신이 늦은 것일 수 있으므로 "
        "EKS 지원 여부는 AWS 콘솔 또는 `aws eks describe-cluster-versions` 로 확인하세요."
    )
    warnings.append(f"Kubernetes {vr.minor}: EKS 지원 여부를 공식 출처로 확인하지 못했습니다 ({'; '.join(support.errors) or '확인 불가'}).")


def _resolve_versions(
    name: str, spec: dict, cluster: ClusterState | None, cli_current: dict, cli_target: dict
) -> tuple[str | None, str, str | None, str]:
    addon = spec.get("eks_addon")
    current, current_src = None, ""
    if name in cli_current:
        current, current_src = cli_current[name], "입력값"
    elif cluster and addon and addon in cluster.addons:
        current, current_src = cluster.addons[addon], "클러스터(EKS add-on)"
    elif cluster and name in cluster.image_versions:
        current, current_src = cluster.image_versions[name], "클러스터(이미지 태그)"

    target, target_src = None, ""
    if name in cli_target:
        target, target_src = cli_target[name], "입력값"
    elif cluster and addon and addon in cluster.addon_defaults and current_src == "클러스터(EKS add-on)":
        target, target_src = cluster.addon_defaults[addon], "목표 EKS 버전의 기본(default) add-on 버전"
    return current, current_src, target, target_src


def build_component_reports(
    http: HttpClient,
    components: dict[str, dict],
    to_minor: str,
    cluster: ClusterState | None,
    cli_current: dict[str, str],
    cli_target: dict[str, str],
    search_issues: bool,
    lookback: int,
    warnings: list[str],
    log: Log,
) -> list[ComponentReport]:
    gh = GitHub(http)
    issues_enabled = search_issues
    reports = []
    for name, spec in components.items():
        repo = spec.get("repo")
        cr = ComponentReport(name=name, repo=repo, eks_addon=spec.get("eks_addon"))
        cr.current, cr.current_source, cr.target, cr.target_source = _resolve_versions(
            name, spec, cluster, cli_current, cli_target
        )
        addon = spec.get("eks_addon")
        if cluster and addon:
            cr.compat = cluster.addon_compat.get(addon)
            if addon not in cluster.addons and name not in cluster.image_versions:
                cr.notes.append("클러스터에서 설치를 확인하지 못했습니다 (미설치 또는 다른 방식으로 설치).")

        if not repo:
            cr.notes.append("Kubernetes 본체와 함께 릴리스되는 컴포넌트입니다. Kubernetes 변경사항 섹션을 참고하세요.")
            reports.append(cr)
            continue

        log(f"  - {name} ({repo}) 릴리스 수집")
        tag_pattern = spec.get("tag_pattern", DEFAULT_TAG_PATTERN)
        try:
            releases = gh.releases(repo)
        except FetchError as e:
            warnings.append(f"{name} 릴리스 수집 실패: {e}")
            cr.fetch_failed = True
            cr.notes.append("릴리스 수집 실패 — 하단 '수집 경고' 참고")
            reports.append(cr)
            continue

        if not cr.target:
            cr.target, cr.target_source = latest_version(releases, tag_pattern), "최신 릴리스"
        # add-on 버전 'v1.19.0-eksbuild.1' 은 업스트림 태그 'v1.19.0' 기준으로 비교
        selected = select_releases(releases, cr.current, cr.target, tag_pattern, lookback)
        if not cr.current:
            cr.notes.append(
                f"현재 버전을 알 수 없어 최근 {lookback}개 릴리스만 분석했습니다. "
                "입력 파일에 현재 버전을 적으면 정확해집니다."
            )
        for r in selected:
            cr.release_tags.append((r.tag, r.url))
            for f in classify_release(r.body, source=r.tag, url=r.url):
                if f.severity == INFO:
                    cr.info_count += 1
                else:
                    cr.findings.append(f)

        if issues_enabled:
            try:
                cr.issues = _search_issues(gh, repo, spec, cr.target, to_minor)
            except RateLimited as e:
                warnings.append(f"이슈 검색 중단: {e}")
                issues_enabled = False
            except FetchError as e:
                warnings.append(f"{name} 이슈 검색 실패: {e}")
        reports.append(cr)
    return reports


def _search_issues(gh: GitHub, repo: str, spec: dict, target: str | None, to_minor: str):
    queries = []
    tv = versions.parse(target)
    if tv:
        queries.append(f'repo:{repo} is:issue is:open "{versions.fmt(tv)}"')
    label = spec.get("bug_label")
    queries.append(
        f'repo:{repo} is:issue is:open "{to_minor}"' + (f' label:"{label}"' if label else "")
    )
    seen, result = set(), []
    for q in queries:
        for issue in gh.search_issues(q, limit=5):
            if issue.number not in seen:
                seen.add(issue.number)
                result.append(issue)
    return result[:8]


def nodegroup_findings(nodegroups: list[NodeGroup], to_minor: str) -> list[Finding]:
    out: list[Finding] = []
    target = versions.parse_minor(to_minor)
    for ng in nodegroups:
        try:
            ngv = versions.parse_minor(ng.version)
        except ValueError:
            continue
        skew = target[1] - ngv[1]
        if skew > KUBELET_MAX_SKEW:
            out.append(Finding(CRITICAL, f"노드그룹 `{ng.name}` ({ng.version})이 목표 버전 {to_minor} 대비 "
                                         f"{skew} 마이너 낮아 kubelet 버전 차이(skew) 허용 범위({KUBELET_MAX_SKEW})를 넘습니다. "
                                         "컨트롤 플레인 업그레이드 중간에 노드그룹도 함께 올려야 합니다."))
        elif skew > 0:
            out.append(Finding(REVIEW, f"노드그룹 `{ng.name}` ({ng.version}): 컨트롤 플레인 업그레이드 후 {to_minor} 로 업그레이드 필요."))
        if ng.ami_type.startswith("AL2_") and target > AL2_LAST_MINOR:
            out.append(Finding(CRITICAL, f"노드그룹 `{ng.name}` 은 AMI 타입 `{ng.ami_type}`(Amazon Linux 2)입니다. "
                                         f"EKS 는 {versions.minor_str(AL2_LAST_MINOR)} 이후 AL2 AMI 를 제공하지 않으므로 "
                                         "AL2023 또는 Bottlerocket 으로 전환해야 합니다."))
    return out


def cluster_findings(state: ClusterState, to_minor: str, components: dict[str, dict]) -> list[Finding]:
    out = nodegroup_findings(state.nodegroups, to_minor)
    for ins in state.insights:
        if ins.status == "ERROR":
            out.append(Finding(CRITICAL, f"Upgrade Insight `{ins.name}` (대상 {ins.kubernetes_version}): {ins.reason}"))
        elif ins.status in ("WARNING", "UNKNOWN"):
            out.append(Finding(REVIEW, f"Upgrade Insight `{ins.name}` [{ins.status}] (대상 {ins.kubernetes_version}): {ins.reason}"))

    for name, spec in components.items():
        addon = spec.get("eks_addon")
        compat = state.addon_compat.get(addon) if addon else None
        if not compat or addon not in state.addons:
            continue
        bad = [m for m, c in compat.per_minor.items() if c.get("current_compatible") is False]
        if bad:
            out.append(Finding(CRITICAL, f"Add-on `{addon}` 현재 버전 {state.addons[addon]} 은 "
                                         f"Kubernetes {', '.join(bad)} 와 호환되지 않습니다. 해당 단계 전에 add-on 을 먼저 올리세요."))
    return sorted(out, key=lambda f: f.severity != CRITICAL)


def run(
    http: HttpClient,
    components: dict[str, dict],
    from_minor: str | None,
    to_minor: str,
    cluster: ClusterState | None = None,
    cluster_warnings: list[str] | None = None,
    cli_current: dict[str, str] | None = None,
    cli_target: dict[str, str] | None = None,
    search_issues: bool = True,
    lookback: int = 5,
    nodegroups: list[NodeGroup] | None = None,
    source: str = "",
    use_aws: bool = True,
    aws_profile: str | None = None,
    aws_region: str | None = None,
    log: Log = lambda _m: None,
) -> Report:
    if cluster:
        if from_minor and from_minor != cluster.version:
            log(f"  ! --from {from_minor} 대신 클러스터 실제 버전 {cluster.version} 을 사용합니다.")
        from_minor = cluster.version
    if not from_minor:
        raise ValueError("--from 또는 --cluster 중 하나는 필요합니다.")
    from_minor = versions.minor_str(versions.parse_minor(from_minor))
    path = versions.upgrade_path(from_minor, to_minor)

    report = Report(
        from_minor=from_minor,
        to_minor=to_minor,
        path=path,
        generated_at=dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        source=source,
        cluster=cluster,
        nodegroups=list(nodegroups or []),
        warnings=list(cluster_warnings or []),
    )
    if cluster:
        report.env_findings = cluster_findings(cluster, to_minor, components)
    elif report.nodegroups:
        report.env_findings = sorted(nodegroup_findings(report.nodegroups, to_minor), key=lambda f: f.severity != CRITICAL)
    log("[1/2] Kubernetes / EKS 변경사항")
    support = eks_versions.resolve(http, use_aws, aws_profile, aws_region, log)
    report.versions = build_version_reports(http, path, report.warnings, log, support)
    log("[2/2] 컴포넌트 릴리스 / 이슈")
    report.components = build_component_reports(
        http, components, to_minor, cluster, cli_current or {}, cli_target or {},
        search_issues, lookback, report.warnings, log,
    )
    return report
