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
    # GitHub 문서 원본은 1.36 까지만 (갱신 지연 상황)
    routes[eks_docs.DOCS["standard"][0]] = "== Kubernetes 1.36\n\n* note 1.36\n\n== Kubernetes 1.35\n\n* note 1.35\n"
    routes[k8s.CHANGELOG_RAW.format(minor="1.37")] = "# v1.37.2\n\n- patch\n\n# v1.37.0\n\n## Changelog since v1.36.0\n"
    routes[k8s.CHANGELOG_RAW.format(minor="1.38")] = "# v1.38.0-alpha.1\n\n- alpha\n"
    return routes


def _api(versions_status, monkeypatch):
    from eks_precheck.sources import eks_versions

    info = eks_versions.SupportInfo(source=eks_versions.SOURCE_API, versions=versions_status,
                                    details={"1.37": {"releaseDate": "2026-10-20"}})
    monkeypatch.setattr(eks_versions, "from_aws_cli", lambda *a, **k: (info, ""))


def test_stale_mirror_does_not_block_when_api_says_supported(fixture_text, fake_http, monkeypatch):
    _api({"1.35": "STANDARD_SUPPORT", "1.36": "STANDARD_SUPPORT", "1.37": "STANDARD_SUPPORT"}, monkeypatch)
    report = precheck.run(fake_http(_eks_status_routes(fixture_text)), {}, "1.35", "1.37")
    v137 = report.versions[1]
    assert v137.eks_status == "standard" and v137.eks_notes_missing
    assert "EKS 출시 2026-10-20" in v137.eks_status_note
    md = render(report)
    assert "업그레이드 불가" not in md
    assert "### Kubernetes 1.37 — EKS standard support" in md


def test_not_yet_only_from_official_source(fixture_text, fake_http, monkeypatch):
    _api({"1.35": "STANDARD_SUPPORT", "1.36": "STANDARD_SUPPORT"}, monkeypatch)
    report = precheck.run(fake_http(_eks_status_routes(fixture_text)), {}, "1.35", "1.38")
    assert [v.eks_status for v in report.versions] == ["standard", "not_yet", "not_yet"]
    assert not report.versions[2].upstream_released
    md = render(report)
    assert "🔴 **업그레이드 불가**: Kubernetes 1.37, 1.38" in md and "AWS API" in md
    assert "가능한 최대 목표 버전은 **1.36**" in md


def test_mirror_only_is_unverified_not_blocker(fixture_text, fake_http):
    # AWS CLI 비활성(기본) + AWS 문서 사이트 접근 실패 → GitHub 원본만 있음
    report = precheck.run(fake_http(_eks_status_routes(fixture_text)), {}, "1.35", "1.37")
    v137 = report.versions[1]
    assert v137.eks_status == "unverified"
    assert any("공식 출처로 확인하지 못했습니다" in w for w in report.warnings)
    md = render(report)
    assert "업그레이드 불가" not in md and "🟡 EKS 지원 여부 확인 필요" in md


def test_live_docs_site_used_when_no_aws_cli(fixture_text, fake_http):
    routes = _eks_status_routes(fixture_text)
    routes[eks_docs.DOCS["standard"][1]] = '<h2 id="kubernetes-1-37">Kubernetes 1.37</h2><h2 id="kubernetes-1-36">x</h2>'
    routes[eks_docs.DOCS["extended"][1]] = '<h2 id="kubernetes-1-33">Kubernetes 1.33</h2>'
    report = precheck.run(fake_http(routes), {}, "1.36", "1.37")
    assert report.versions[0].eks_status == "standard"
    assert report.versions[0].eks_status_source == "AWS 문서 사이트"


def test_ended_from_api(fixture_text, fake_http, monkeypatch):
    _api({"1.30": "UNSUPPORTED", "1.31": "EXTENDED_SUPPORT"}, monkeypatch)
    report = precheck.run(fake_http(_eks_status_routes(fixture_text)), {}, "1.29", "1.31")
    assert [v.eks_status for v in report.versions] == ["ended", "extended"]
