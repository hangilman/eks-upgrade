"""Report 모델 -> 한국어 Markdown."""

from __future__ import annotations

from . import checkpoints
from .models import CRITICAL, REVIEW, SECURITY, ComponentReport, Report, VersionReport

ICON = {CRITICAL: "🔴", REVIEW: "🟡", SECURITY: "🔒"}
ROLLBACK_DOC = "https://docs.aws.amazon.com/eks/latest/userguide/rollback-cluster.html"


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _bullets(items: list[str], limit: int) -> list[str]:
    lines = [f"- {i}" for i in items[:limit]]
    if len(items) > limit:
        lines.append(f"- _…외 {len(items) - limit}건 (원문 링크 참고)_")
    return lines


def _count(report: Report) -> dict[str, int]:
    c = {CRITICAL: 0, REVIEW: 0, SECURITY: 0, "issues": 0}
    for f in report.env_findings:
        c[f.severity] = c.get(f.severity, 0) + 1
    for v in report.versions:
        c[CRITICAL] += len(v.removed_apis) + len(v.eks_important) + len(v.urgent_notes) + (v.eks_status == "not_yet")
        c[REVIEW] += len(v.eks_subsections) + len(v.deprecations) + len(v.api_changes) + (v.eks_status == "unverified")
    for comp in report.components:
        for f in comp.findings:
            c[f.severity] = c.get(f.severity, 0) + 1
        c["issues"] += len(comp.issues)
    return c


def _cluster_section(report: Report) -> list[str]:
    s = report.cluster
    assert s is not None
    out = ["## 1. 클러스터 현황", ""]
    out += [
        f"- 클러스터: `{s.name}` ({s.region})",
        f"- 컨트롤 플레인: `{s.version}` (platform `{s.platform_version}`)",
        "",
    ]
    if report.env_findings:
        out += ["### 클러스터 점검 결과", ""]
        out += [f"- {ICON[f.severity]} {f.text}" for f in report.env_findings]
        out.append("")
    if s.nodegroups:
        out += ["### Managed Node Group", "", "| 이름 | 버전 | AMI 타입 | AMI 릴리스 | Capacity |", "|---|---|---|---|---|"]
        out += [
            f"| {n.name} | {n.version} | {n.ami_type} | {n.release_version} | {n.capacity_type} |"
            for n in s.nodegroups
        ]
        out += ["", "> Karpenter / self-managed 노드는 위 표에 포함되지 않습니다. `kubectl get nodes -o wide` 로 kubelet 버전을 별도 확인하세요.", ""]
        out += _ami_section(report)
    if s.insights:
        out += ["### EKS Upgrade Insights", "", "| 상태 | 항목 | 대상 버전 | 사유 |", "|---|---|---|---|"]
        order = {"ERROR": 0, "WARNING": 1, "UNKNOWN": 2, "PASSING": 3}
        for i in sorted(s.insights, key=lambda x: order.get(x.status, 9)):
            out.append(f"| {i.status} | {_esc(i.name)} | {i.kubernetes_version} | {_esc(i.reason)} |")
        out.append("")
        for i in s.insights:
            if i.status == "PASSING" or not (i.recommendation or i.deprecations):
                continue
            out += [f"**{i.name}**", ""]
            if i.recommendation:
                out += [f"- 권고: {_esc(i.recommendation)}"]
            for d in i.deprecations:
                out.append(
                    f"- `{d.get('usage', '')}` → `{d.get('replacedWith', '-')}` "
                    f"(제거 버전 {d.get('stopServingVersion', '-')})"
                )
                for cs in d.get("clientStats", [])[:5]:
                    out.append(
                        f"  - client `{cs.get('userAgent', '')}`: 최근 30일 {cs.get('numberOfRequestsLast30Days', 0)}회, "
                        f"마지막 {cs.get('lastRequestTime', '')}"
                    )
            out.append("")
    return out


def _version_counts(v: VersionReport) -> dict[str, int]:
    return {
        "제거 API": len(v.removed_apis), "EKS 중요 공지": len(v.eks_important), "Urgent Upgrade Notes": len(v.urgent_notes),
        "EKS 변경 상세": len(v.eks_subsections), "Deprecation": len(v.deprecations), "API Change": len(v.api_changes),
    }


def _version_points(v: VersionReport, limit: int | None = None) -> list:
    critical = [f"{r.resource} {r.summary} 제거되는 API" for r in v.removed_apis] + v.eks_important + v.urgent_notes
    review = [f"{t} {b}" for t, b in v.eks_subsections] + v.deprecations + v.api_changes
    return checkpoints.prioritized(critical, review, limit)


def _component_points(c: ComponentReport, limit: int | None = None) -> list:
    return checkpoints.prioritized([f.text for f in c.findings if f.severity == CRITICAL],
                                   [f.text for f in c.findings if f.severity != CRITICAL], limit)


def _version_severity(v: VersionReport) -> tuple[int, int]:
    c = _version_counts(v)
    crit = c["제거 API"] + c["EKS 중요 공지"] + c["Urgent Upgrade Notes"] + (v.eks_status == "not_yet")
    review = c["EKS 변경 상세"] + c["Deprecation"] + c["API Change"] + (v.eks_status == "unverified")
    return crit, review


def _summary_block(counts: dict[str, int], points: list) -> list[str]:
    nonzero = [f"{k} {n}건" for k, n in counts.items() if n]
    out = ["#### 📋 요약", "", "- " + (" · ".join(nonzero) if nonzero else "업그레이드 영향 항목이 없습니다."), ""]
    if points:
        out += ["#### 🔍 점검 포인트", ""] + checkpoints.render(points) + [""]
    return out


def _version_section(v: VersionReport, limit: int) -> list[str]:
    status = {"standard": "EKS standard support", "extended": "EKS extended support (추가 비용)",
              "not_yet": "🔴 EKS 미지원 (아직 출시 전)", "ended": "EKS 지원 종료",
              "unverified": "🟡 EKS 지원 여부 확인 필요", "unknown": "확인 필요"}[v.eks_status]
    out = [f"### Kubernetes {v.minor} — {status}", ""]
    out.append("링크: " + " · ".join(f"[{k}]({u})" for k, u in v.links.items()))
    out.append("")
    if v.eks_status_source:
        out += [f"- EKS 지원 상태 출처: {v.eks_status_source}", ""]
    if v.eks_status_note:
        icon = {"not_yet": "🔴", "unverified": "🟡"}.get(v.eks_status, "ℹ️")
        out += [f"> {icon} {v.eks_status_note}", ""]
    if not v.upstream_released:
        out += [f"> ℹ️ 업스트림 Kubernetes 에도 아직 v{v.minor}.0 정식 릴리스가 없어 변경사항을 수집하지 못했습니다.", ""]
    out += _summary_block(_version_counts(v), _version_points(v))
    if v.removed_apis:
        out += ["#### 🔴 제거되는 API (더 이상 serve 되지 않음)", ""]
        for r in v.removed_apis:
            out.append(f"- **{r.resource}**: {r.summary}")
            out += [f"  - {b}" for b in r.bullets]
        out.append("")
    if v.eks_important:
        out += ["#### 🔴 EKS 중요 공지", ""] + _bullets(v.eks_important, limit) + [""]
    if v.urgent_notes:
        out += ["#### 🔴 Kubernetes Urgent Upgrade Notes", ""] + _bullets(v.urgent_notes, limit) + [""]
    if v.eks_subsections:
        out += ["#### 🟡 EKS 변경사항 상세", ""]
        out += [f"- **{t}**: {b}" for t, b in v.eks_subsections] + [""]
    if v.deprecations:
        out += ["#### 🟡 Deprecation", ""] + _bullets(v.deprecations, limit) + [""]
    if v.api_changes:
        out += ["#### 🟡 API Change (제거/Deprecation/Action required 관련만)", ""] + _bullets(v.api_changes, limit) + [""]
    if v.eks_notes:
        out += ["#### ℹ️ EKS 주요 변경", ""] + _bullets(v.eks_notes, limit) + [""]
    return out


def _component_section(c: ComponentReport, limit: int, target_minor: str) -> list[str]:
    kind = {"eks-addon": " · EKS 관리형 add-on", "helm": " · Helm / 직접 설치"}.get(c.install, "")
    title = f"### {c.name}{kind}" + (f" ([{c.repo}](https://github.com/{c.repo}))" if c.repo else "")
    out = [title, ""]
    cur = f"`{c.current}` ({c.current_source})" if c.current else "알 수 없음"
    tgt = f"`{c.target}` ({c.target_source})" if c.target else "-"
    out += [f"- 현재: {cur}", f"- 목표: {tgt}"]
    if c.install == "helm":
        out.append("- 버전 기준: 애플리케이션 버전 (`helm list -A` 의 **APP VERSION** 열, CHART 버전과 다를 수 있음)")
    if c.release_tags:
        tags = ", ".join(f"[{t}]({u})" for t, u in c.release_tags)
        out.append(f"- 분석한 릴리스 ({len(c.release_tags)}개): {tags}")
    out += [f"- ℹ️ {n}" for n in c.notes]
    out.append("")

    counts = {label: sum(1 for f in c.findings if f.severity == sev)
              for sev, label in ((CRITICAL, "Breaking / Action required"), (SECURITY, "보안 수정"), (REVIEW, "Deprecation / 동작 변경"))}
    counts["관련 오픈 이슈"] = len(c.issues)
    if c.repo and not c.fetch_failed:
        out += _summary_block(counts, _component_points(c))

    if c.compat and c.compat.per_minor:
        out += ["| Kubernetes | 현재 버전 호환 | 기본(default) 버전 | 최신 버전 |", "|---|---|---|---|"]
        for minor, info in c.compat.per_minor.items():
            ok = {True: "✅", False: "❌", None: "-"}[info.get("current_compatible")]
            out.append(f"| {minor} | {ok} | {info.get('default') or '-'} | {info.get('latest') or '-'} |")
        out.append("")
    elif c.eks_addon:
        out += [
            "- 목표 EKS 버전과의 호환 add-on 버전 확인 (AWS CLI, Windows/Linux 공통):",
            "",
            "  ```",
            f"  aws eks describe-addon-versions --addon-name {c.eks_addon} --kubernetes-version {target_minor} "
            '--query "addons[].addonVersions[].[addonVersion, compatibilities[0].defaultVersion]" --output table',
            "  ```",
            "",
        ]

    for sev, label in ((CRITICAL, "Breaking / Action required"), (SECURITY, "보안 수정"), (REVIEW, "Deprecation / 동작 변경")):
        items = [f for f in c.findings if f.severity == sev]
        if not items:
            continue
        out += [f"#### {ICON[sev]} {label} ({len(items)})", ""]
        for f in items[:limit]:
            out.append(f"- [{f.source}]({f.url}) {f.text}")
        if len(items) > limit:
            out.append(f"- _…외 {len(items) - limit}건_")
        out.append("")
    if c.info_count:
        out += [f"_그 외 일반 변경 {c.info_count}건은 생략했습니다._", ""]
    if c.issues:
        out += ["#### 🐛 관련 오픈 이슈 (최근 업데이트 순)", ""]
        out += [f"- [#{i.number}]({i.url}) {_esc(i.title)} _(updated {i.updated_at})_" for i in c.issues]
        out.append("")
    return out


def _checklist(report: Report) -> list[str]:
    out = ["## 사전 점검 체크리스트", ""]
    items = [
        "위 🔴 항목을 모두 검토하고 조치 담당자를 지정했다",
        "EKS 콘솔 또는 `aws eks list-insights --cluster-name <name>` 에서 Upgrade Insights 가 모두 PASSING 이다",
        "제거되는 API 사용 여부를 매니페스트/Helm chart 에서도 확인했다 (예: `pluto detect-files`, `kubent`)",
        "각 업그레이드 단계(" + " → ".join([report.from_minor, *report.path]) + ")마다 add-on 이 호환되는 버전인지 확인했다",
        "클러스터 서브넷에 가용 IP 가 충분하다 (EKS 는 컨트롤 플레인 업그레이드 시 최대 5개의 IP 필요)",
        "PDB 때문에 노드 drain 이 막히지 않는다: `kubectl get pdb -A` 에서 ALLOWED DISRUPTIONS 0 인 항목 확인",
        "노드 kubelet 버전 차이(skew)가 허용 범위 안이다: `kubectl get nodes`",
        "Karpenter/Cluster Autoscaler, ALB Controller 등 컨트롤러의 목표 Kubernetes 버전 지원 여부를 확인했다",
        "매니페스트/리소스 백업(GitOps 레포, Velero 등)이 최신이다",
        "stg/dev 클러스터에서 동일 절차로 먼저 검증했다",
    ]
    out += [f"- [ ] {i}" for i in items]
    out += [
        "",
        "### 롤백 계획",
        "",
        f"EKS 는 in-place 업그레이드 후 컨트롤 플레인을 직전 버전으로 되돌리는 [버전 롤백]({ROLLBACK_DOC}) 을 지원합니다. "
        "주요 조건은 아래와 같으며, 실제 작업 전 문서에서 최신 조건을 다시 확인하세요.",
        "",
        "- 업그레이드 완료 후 **7일 이내**, **한 단계(N → N-1)만** 가능합니다. "
        f"여러 단계({' → '.join([report.from_minor, *report.path])})를 연속으로 올리면 마지막 단계만 되돌릴 수 있습니다.",
        "- **EKS add-on, 관리형 노드그룹, self-managed 노드는 함께 롤백되지 않습니다.** 노드는 컨트롤 플레인보다 먼저 되돌리고, "
        "add-on 은 이전 버전과 호환되는 버전으로 별도 다운그레이드해야 합니다.",
        "- etcd 데이터와 workload 는 유지됩니다. 롤백 전 rollback readiness insight 를 확인하세요.",
        "- 롤백 조건을 벗어나는 경우(7일 경과 등)를 대비해 하위 환경 선검증과 Blue/Green 전환 계획은 계속 유지하는 것을 권장합니다.",
        "",
    ]
    return out


def _impact_table(report: Report) -> list[str]:
    """입력한 컴포넌트별 영향도를 한눈에 보는 표."""
    if not report.components:
        return []
    out = [
        "### 컴포넌트별 영향도",
        "",
        "| 컴포넌트 | 현재 → 목표 | 분석 릴리스 | 🔴 | 🔒 | 🟡 | 🐛 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in report.components:
        cnt = {s: sum(1 for f in c.findings if f.severity == s) for s in (CRITICAL, SECURITY, REVIEW)}
        span = f"{c.current or '?'} → {c.target or '?'}" if c.repo else f"{c.current or '?'} (Kubernetes 와 함께 변경)"
        rel = "⚠️ 수집 실패" if c.fetch_failed else (str(len(c.release_tags)) if c.repo else "-")
        out.append(
            f"| {c.name} | {span} | {rel} | {cnt[CRITICAL] or ''} | {cnt[SECURITY] or ''} | {cnt[REVIEW] or ''} | {len(c.issues) or ''} |"
        )
    return out + [""]


def _section_summary(report: Report) -> list[str]:
    """요약 화면용: 항목별 🔴/🟡 건수와 먼저 볼 점검 포인트."""
    rows = []
    for v in report.versions:
        crit, review = _version_severity(v)
        points = _version_points(v, limit=3)
        rows.append((f"Kubernetes {v.minor}", crit, review, points))
    for c in report.components:
        if not c.repo or c.fetch_failed:
            continue
        crit = sum(1 for f in c.findings if f.severity == CRITICAL)
        review = sum(1 for f in c.findings if f.severity in (REVIEW, SECURITY))
        rows.append((c.name, crit, review, _component_points(c, limit=3)))
    if not rows:
        return []
    out = ["### 항목별 점검 요약", "", "| 항목 | 🔴 | 🟡 | 먼저 확인할 것 |", "|---|---|---|---|"]
    for name, crit, review, points in rows:
        todo = " / ".join(p.title for p in points) or "-"
        out.append(f"| {name} | {crit or ''} | {review or ''} | {_esc(todo)} |")
    return out + [""]


def _ami_section(report: Report) -> list[str]:
    if not report.amis:
        return []
    out = ["### 권장 EKS 최적화 AMI (조회 시점 기준)", "",
           "| 노드그룹 | AMI 타입 | 사용 중 AMI (입력) | 현재 버전 권장 AMI | 목표 버전 권장 AMI |", "|---|---|---|---|---|"]
    by_name = {g.name: g for g in (report.cluster.nodegroups if report.cluster else report.nodegroups)}

    def cell(info) -> str:
        if info.image_id:
            rel = f" · {info.release_version}" if info.release_version else ""
            return f"`{info.image_id}` ({info.minor}){rel}"
        return f"- ({info.minor})"

    for name, pair in report.amis.items():
        g = by_name.get(name)
        used = f"`{g.ami_id}`" if g and g.ami_id else "-"
        out.append(f"| {name} | {pair['current'].ami_type} | {used} | {cell(pair['current'])} | {cell(pair['target'])} |")
    infos = [i for pair in report.amis.values() for i in pair.values()]
    ok = next((i for i in infos if i.image_id), None)
    out.append("")
    if ok:
        out.append(f"- 조회: {ok.queried_at}, 리전 `{ok.region or 'AWS CLI 기본값'}`. AMI ID 는 리전별로 다르며, "
                   "AWS 가 새 AMI 를 릴리스하면 권장 값이 바뀝니다. Launch Template 에는 작업 직전에 다시 확인한 값을 넣으세요.")
    errors = {(i.ami_type, i.minor): i for i in infos if i.error and not i.extra.get("missing")}
    if errors:
        out.append("- 조회하지 못한 항목은 아래 명령으로 직접 확인할 수 있습니다:")
        out.append("")
        out.append("  ```")
        out += [f"  {i.command}" for i in errors.values() if i.parameter]
        out.append("  ```")
        reasons = sorted({i.error for i in errors.values()})
        out += [f"  - 사유: {r}" for r in reasons]
    missing = [i for i in infos if i.extra.get("missing")]
    for i in missing:
        out.append(f"- ⚠️ {i.error}")
    return out + [""]


def _nodegroup_input_section(report: Report, n: int) -> list[str]:
    out = [f"## {n}. 노드그룹 점검 (입력값 기준)", ""]
    if report.env_findings:
        out += [f"- {ICON[f.severity]} {f.text}" for f in report.env_findings]
    else:
        out.append("- ✅ AMI 타입 / 버전 차이(skew) 문제 없음")
    out.append("")
    return out + _ami_section(report)


def _blockers(report: Report) -> list[str]:
    """업그레이드 자체가 불가능한 조건은 리포트 맨 위에 표시."""
    not_yet = [v.minor for v in report.versions if v.eks_status == "not_yet"]
    if not not_yet:
        return []
    supported = [v.minor for v in report.versions if v.eks_status in ("standard", "extended")]
    tail = f" 현재 EKS 에서 가능한 최대 목표 버전은 **{supported[-1]}** 입니다." if supported else ""
    return [
        f"> 🔴 **업그레이드 불가**: Kubernetes {', '.join(not_yet)} 는 아직 Amazon EKS 에서 지원되지 않습니다 "
        f"({report.versions[-1].eks_status_source} 기준).{tail} "
        "아래 내용은 EKS 지원 이후를 대비한 업스트림 기준 참고 정보입니다.",
        "",
    ]


def render(report: Report, limit: int = 20) -> str:
    c = _count(report)
    path = " → ".join([report.from_minor, *report.path])
    if report.cluster:
        target_line = f"- 대상 클러스터: `{report.cluster.name}` (read-only 조회)"
    else:
        target_line = f"- 입력: `{report.source}`" if report.source else "- 입력: 직접 지정"
    out = [
        f"# EKS 업그레이드 사전 점검 리포트: {report.from_minor} → {report.to_minor}",
        "",
        f"- 생성 시각: {report.generated_at}",
        f"- 업그레이드 경로: {path} (컨트롤 플레인은 한 번에 1 마이너씩만 업그레이드 가능)",
        target_line,
        "",
        *_blockers(report),
        "> 이 리포트는 공개 문서/Release note 를 규칙 기반으로 자동 추출한 결과입니다. "
        "누락이나 오분류가 있을 수 있으므로 최종 판단 전 원문 링크를 확인하세요.",
        "",
        "## 요약",
        "",
        "| 구분 | 건수 |",
        "|---|---|",
        f"| 🔴 필수 확인 / 조치 | {c[CRITICAL]} |",
        f"| 🟡 검토 필요 | {c[REVIEW]} |",
        f"| 🔒 보안 수정 | {c[SECURITY]} |",
        f"| 🐛 관련 오픈 이슈 | {c['issues']} |",
        f"| ⚠️ 수집 경고 | {len(report.warnings)} |",
        "",
    ]
    out += _impact_table(report)
    out += _section_summary(report)
    n = 1
    if report.cluster:
        out += _cluster_section(report)
        n += 1
    elif report.nodegroups:
        out += _nodegroup_input_section(report, n)
        n += 1
    out += [f"## {n}. Kubernetes / EKS 변경사항", ""]
    for v in report.versions:
        out += _version_section(v, limit)
    out += [f"## {n + 1}. Add-on / 컴포넌트", ""]
    if not report.components:
        out += ["_입력한 add-on 이 없습니다. 입력 파일의 `addons:` 에 사용 중인 add-on 과 버전을 적으면 함께 분석합니다._", ""]
    for comp in report.components:
        out += _component_section(comp, limit, report.to_minor)
    out += _checklist(report)
    if report.warnings:
        out += ["## 수집 경고", ""] + [f"- {w}" for w in report.warnings] + [""]
    return "\n".join(out).rstrip() + "\n"
