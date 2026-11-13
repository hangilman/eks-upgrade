from eks_precheck import precheck
from eks_precheck.cluster import images_to_versions
from eks_precheck.models import CRITICAL, REVIEW, AddonCompat, ClusterState, Insight, NodeGroup
from eks_precheck.report import render
from eks_precheck.sources import eks_docs, k8s
from eks_precheck.sources.github import API, Release, select_releases


def _rel(tag, body="", prerelease=False):
    return {"tag_name": tag, "name": tag, "body": body, "html_url": f"https://gh/{tag}",
            "published_at": "", "prerelease": prerelease, "draft": False}


RELEASES = [
    _rel("v1.20.0", "## Breaking\n* removed legacy mode"),
    _rel("v1.19.2", "* fix: CVE-2025-0001 patched"),
    _rel("v1.19.1-rc.1", "* rc", prerelease=True),
    _rel("helm-chart-2.0.0", "* chart"),
    _rel("v1.19.0", "* Deprecate old flag"),
    _rel("v1.18.0", "* old"),
]


def test_select_releases_range():
    rels = [Release(r["tag_name"], "", r["body"], "", "", r["prerelease"], False) for r in RELEASES]
    tags = [r.tag for r in select_releases(rels, "v1.18.0-eksbuild.1", "v1.19.2")]
    assert tags == ["v1.19.0", "v1.19.2"]
    assert [r.tag for r in select_releases(rels, None, None, lookback=2)] == ["v1.19.2", "v1.20.0"]


def _routes(fixture_text):
    return {
        k8s.DEPRECATION_GUIDE_RAW: fixture_text("deprecation-guide.md"),
        eks_docs.DOCS["extended"][0]: fixture_text("kubernetes-versions-extended.adoc"),
        k8s.CHANGELOG_RAW.format(minor="1.31"): fixture_text("CHANGELOG-1.31.md"),
        f"{API}/repos/aws/amazon-vpc-cni-k8s/releases": RELEASES,
        f"{API}/search/issues": {"items": [
            {"number": 7, "title": "v1.20.0 crash on start", "html_url": "https://gh/i/7", "updated_at": "2026-01-01T00:00:00Z", "labels": [{"name": "bug"}]},
            {"number": 8, "title": "a PR", "html_url": "https://gh/p/8", "updated_at": "", "labels": [], "pull_request": {}},
        ]},
    }


COMPONENTS = {
    "vpc-cni": {"repo": "aws/amazon-vpc-cni-k8s", "eks_addon": "vpc-cni", "bug_label": "bug"},
    "kube-proxy": {"eks_addon": "kube-proxy"},
}


def test_offline_run_end_to_end(fixture_text, fake_http):
    http = fake_http(_routes(fixture_text))
    report = precheck.run(http, COMPONENTS, "1.30", "1.31", cli_current={"vpc-cni": "v1.19.0"})

    assert report.path == ["1.31"]
    v = report.versions[0]
    assert v.urgent_notes and v.deprecations
    # 수집 실패/섹션 없음은 경고로 기록되고 실행은 계속됨
    assert any("EKS 문서(standard)" in w for w in report.warnings)
    assert any("Kubernetes 1.31: EKS 문서 일부를 수집하지 못해" in w for w in report.warnings)

    vpc = report.components[0]
    assert vpc.target == "v1.20.0" and vpc.target_source == "최신 릴리스"
    assert [t for t, _ in vpc.release_tags] == ["v1.19.2", "v1.20.0"]
    assert {f.severity for f in vpc.findings} == {CRITICAL, "security"}
    assert [i.number for i in vpc.issues] == [7]  # PR 은 제외, 중복 제거

    md = render(report)
    assert "# EKS 업그레이드 사전 점검 리포트: 1.30 → 1.31" in md
    assert "removed legacy mode" in md and "[#7](https://gh/i/7)" in md
    assert "롤백 주의" in md


def test_rate_limit_stops_issue_search(fixture_text, fake_http):
    from eks_precheck.http import RateLimited

    routes = _routes(fixture_text)
    routes[f"{API}/search/issues"] = RateLimited("limit")
    comps = {"a": COMPONENTS["vpc-cni"], "b": COMPONENTS["vpc-cni"]}
    http = fake_http(routes)
    report = precheck.run(http, comps, "1.30", "1.31")
    searches = [u for u, _ in http.calls if u.endswith("/search/issues")]
    assert len(searches) == 1  # 첫 rate limit 이후 이슈 검색 중단
    assert any("이슈 검색 중단" in w for w in report.warnings)


def test_cluster_findings():
    state = ClusterState(
        name="c", region="ap-northeast-2", version="1.32",
        addons={"vpc-cni": "v1.18.0-eksbuild.1"},
        nodegroups=[NodeGroup("old", "1.29", "AL2_x86_64"), NodeGroup("new", "1.32", "AL2023_x86_64_STANDARD")],
        insights=[Insight("1", "Deprecated APIs removed in 1.33", "ERROR", "in use", "1.33"),
                  Insight("2", "Kubelet skew", "PASSING", "", "1.33")],
        addon_compat={"vpc-cni": AddonCompat({"1.32": {"current_compatible": True}, "1.33": {"current_compatible": False}})},
    )
    findings = precheck.cluster_findings(state, "1.33", {"vpc-cni": {"eks_addon": "vpc-cni"}})
    crit = [f.text for f in findings if f.severity == CRITICAL]
    assert any("`old`" in t and "skew" in t for t in crit)
    assert any("AL2_x86_64" in t for t in crit)
    assert any("Deprecated APIs" in t for t in crit)
    assert any("vpc-cni" in t and "1.33" in t for t in crit)
    assert any("`new`" in f.text for f in findings if f.severity == REVIEW)
    assert not any("Kubelet skew" in f.text for f in findings)


def test_images_to_versions():
    obj = {"items": [{"spec": {"template": {"spec": {"containers": [
        {"image": "public.ecr.aws/karpenter/controller:1.0.6@sha256:abc"},
        {"image": "602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon/aws-load-balancer-controller:v2.8.1"},
        {"image": "registry/foo:latest"},
    ]}}}}]}
    comps = {"karpenter": {"image_match": "karpenter/controller:"},
             "aws-load-balancer-controller": {"image_match": "aws-load-balancer-controller:"},
             "foo": {"image_match": "foo:"}}
    assert images_to_versions(obj, comps) == {"karpenter": "1.0.6", "aws-load-balancer-controller": "v2.8.1"}


def _eks_status_routes(fixture_text):
    routes = _routes(fixture_text)
    routes[eks_docs.DOCS["standard"][0]] = "== Kubernetes 1.36\n\n* note 1.36\n\n== Kubernetes 1.35\n\n* note 1.35\n"
    routes[k8s.CHANGELOG_RAW.format(minor="1.37")] = "# v1.37.2\n\n- patch\n\n# v1.37.0\n\n## Changelog since v1.36.0\n"
    routes[k8s.CHANGELOG_RAW.format(minor="1.38")] = "# v1.38.0-alpha.1\n\n- alpha\n"
    return routes


def test_target_not_yet_supported_by_eks(fixture_text, fake_http):
    report = precheck.run(fake_http(_eks_status_routes(fixture_text)), {}, "1.35", "1.38")
    status = {v.minor: v.eks_status for v in report.versions}
    assert status == {"1.36": "standard", "1.37": "not_yet", "1.38": "not_yet"}
    assert "최신 버전: 1.36" in report.versions[1].eks_status_note
    assert not report.versions[2].upstream_released
    assert not any("지원 종료" in w for w in report.warnings)

    md = render(report)
    assert "🔴 **업그레이드 불가**: Kubernetes 1.37, 1.38" in md
    assert "가능한 최대 목표 버전은 **1.36**" in md
    assert "### Kubernetes 1.37 — 🔴 EKS 미지원 (아직 출시 전)" in md


def test_ended_and_unknown_status(fixture_text, fake_http):
    routes = _eks_status_routes(fixture_text)
    report = precheck.run(fake_http(routes), {}, "1.29", "1.30")
    assert report.versions[0].eks_status == "ended"  # 1.30 < 문서 최저 버전(1.31)

    del routes[eks_docs.DOCS["standard"][0]]  # 문서 일부 수집 실패 → 판단 보류
    report = precheck.run(fake_http(routes), {}, "1.36", "1.37")
    assert report.versions[0].eks_status == "unknown"
    assert any("판단할 수 없습니다" in w for w in report.warnings)
