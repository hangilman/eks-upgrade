from eks_precheck import checkpoints
from eks_precheck.models import CRITICAL, REVIEW, ComponentReport, Finding, Report, VersionReport
from eks_precheck.report import render


def keys(points):
    return [p.key for p in points]


def test_rules_match_keywords():
    texts = ["Kubernetes 1.35 deprecates cgroup v1 support", "Containerd 1.x End of Support",
             "In March 2026, the upstream Kubernetes project will retire Ingress NGINX"]
    assert keys(checkpoints.match(texts)) == ["cgroup", "containerd", "ingress-nginx"]
    assert checkpoints.match(["nothing relevant here"]) == []


def test_critical_first_and_generic_only_from_critical():
    points = checkpoints.prioritized(
        critical=["ACTION REQUIRED: webhook certificates must be rotated"],
        review=["Removed feature gate Foo", "cgroup v1 is deprecated"])
    assert keys(points) == ["webhook", "cgroup"]  # feature-gate 는 🟡 에서만 나와서 제외
    points = checkpoints.prioritized(critical=["Removed feature gate Foo"], review=[])
    assert keys(points) == ["feature-gate"]


def test_commands_are_shell_safe():
    for _pattern, cp in checkpoints._RULES:
        for cmd in cp.commands:
            assert "|" not in cmd and " grep " not in cmd  # PowerShell / bash 공통
            if "$" in cmd or "\\" in cmd:
                assert "'" in cmd  # 변수/역슬래시는 작은따옴표로 보호


def test_report_has_section_summary_and_points():
    v = VersionReport(minor="1.35", eks_status="standard",
                      eks_important=["Kubernetes 1.35 deprecates cgroup v1 support"],
                      deprecations=["Marked ipvs mode in kube-proxy as deprecated"])
    c = ComponentReport(name="aws-load-balancer-controller", repo="kubernetes-sigs/aws-load-balancer-controller",
                        install="helm", current="v2.8.1", target="v2.11.0",
                        findings=[Finding(CRITICAL, "Breaking: update the IAM policy to add elasticloadbalancing:AddTags"),
                                  Finding(REVIEW, "CRDs updated for TargetGroupBinding")])
    md = render(Report(from_minor="1.34", to_minor="1.35", path=["1.35"], generated_at="t", versions=[v], components=[c]))
    assert "### 항목별 점검 요약" in md
    assert "| Kubernetes 1.35 | 1 | 1 | 노드 OS 의 cgroup 버전" in md
    assert "| aws-load-balancer-controller | 1 | 1 | 컨트롤러 IAM 역할 정책" in md
    assert md.count("#### 📋 요약") == 2 and md.count("#### 🔍 점검 포인트") == 2
    assert "- EKS 중요 공지 1건 · Deprecation 1건" in md
