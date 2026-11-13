import json
import threading
import time

import pytest
import requests

from eks_precheck import server


@pytest.fixture
def ui(tmp_path, fixture_text, fake_http):
    from test_precheck import _routes

    (tmp_path / "env.yaml").write_text('cluster: {current: "1.30", target: "1.31"}\naddons: {vpc-cni: "v1.19.0"}\n', encoding="utf-8")
    app = server.App(tmp_path, http_factory=lambda no_cache: fake_http(_routes(fixture_text)))
    srv = server.create_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    session = requests.Session()
    session.trust_env = False  # 테스트 환경의 프록시 설정 무시
    yield base, session, tmp_path
    srv.shutdown()
    srv.server_close()


def test_page_and_init(ui, monkeypatch):
    base, s, _ = ui
    monkeypatch.setattr(server, "resolve_token", lambda: None)
    assert "EKS 업그레이드 사전 점검" in s.get(base + "/").text
    init = s.get(base + "/api/init").json()
    assert "vpc-cni" in init["components"]
    assert init["env"]["cluster"] == {"current": "1.30", "target": "1.31"}  # env.yaml 에서 초기값
    assert init["github_token"] is False


def test_run_job_and_read_report(ui):
    base, s, tmp = ui
    payload = {"cluster": {"current": "1.30", "target": "1.31"},
               "addons": {"vpc-cni": {"current": "v1.19.0-eksbuild.1", "target": ""}},
               "nodegroups": [{"name": "old", "version": "1.27", "ami_type": "AL2_x86_64"}],
               "options": {"no_aws": True}}
    res = s.post(base + "/api/run", json=payload)
    assert res.status_code == 202
    job = res.json()["job"]
    for _ in range(50):
        state = s.get(f"{base}/api/jobs/{job}").json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] == "done", state
    rep = state["report"]
    assert "<h1" in rep["html"] and "컴포넌트별 영향도" in rep["markdown"]
    assert (tmp / "reports" / rep["name"]).exists()
    assert rep["name"] in s.get(base + "/api/reports").json()["reports"]
    assert s.get(f"{base}/api/reports/{rep['name']}").json()["markdown"] == rep["markdown"]


def test_input_error_returns_400(ui):
    base, s, _ = ui
    res = s.post(base + "/api/run", json={"cluster": {"current": "1.31", "target": "1.30"}})
    assert res.status_code == 400 and "높아야" in res.json()["error"]


def test_rejects_foreign_origin_host_and_non_json(ui):
    base, s, _ = ui
    port = base.rsplit(":", 1)[1]
    body = json.dumps({"cluster": {"current": "1.30", "target": "1.31"}})
    headers = {"Content-Type": "application/json", "Origin": "https://evil.example"}
    assert s.post(base + "/api/run", data=body, headers=headers).status_code == 403
    assert s.post(base + "/api/run", data=body, headers={"Content-Type": "text/plain"}).status_code == 415
    assert s.get(base + "/api/init", headers={"Host": f"evil.example:{port}"}).status_code == 403


def test_report_path_traversal_blocked(ui):
    base, s, _ = ui
    assert s.get(base + "/api/reports/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_cluster_versions_endpoint(ui, monkeypatch):
    from eks_precheck.sources import eks_versions

    base, s, _ = ui
    info = eks_versions.SupportInfo(source=eks_versions.SOURCE_API,
                                    versions={"1.37": "STANDARD_SUPPORT", "1.33": "EXTENDED_SUPPORT"})
    monkeypatch.setattr(eks_versions, "from_aws_cli", lambda *a, **k: (info, ""))
    data = s.get(base + "/api/versions").json()
    assert data["source"].startswith("AWS API")
    vs = {v["minor"]: v["status"] for v in data["versions"]}
    assert vs["1.37"] == "standard" and vs["1.33"] == "extended"
    assert vs["1.32"] == "ended"  # 예전 버전도 '현재 버전' 선택용으로 포함
    assert [v["minor"] for v in data["versions"]][0] == "1.37"  # 최신순


def test_cluster_versions_fallback_to_mirror(ui):
    base, s, _ = ui
    # AWS CLI 비활성(conftest) + 문서 사이트 없음 → GitHub 문서 원본(extended fixture: 1.32, 1.33)
    data = s.get(base + "/api/versions").json()
    assert "확인 필요" in data["source"]
    vs = {v["minor"]: v["status"] for v in data["versions"]}
    assert vs["1.33"] == "unverified"
    assert "1.34" not in vs  # 업스트림 CHANGELOG-1.34 가 없으면 추가하지 않음


def test_cluster_versions_adds_upstream_released(tmp_path, fixture_text, fake_http):
    from test_precheck import _eks_status_routes

    routes = _eks_status_routes(fixture_text)  # 문서 원본은 1.36 까지, 업스트림 1.37.0 출시, 1.38 은 alpha
    app = server.App(tmp_path, http_factory=lambda no_cache: fake_http(routes))
    vs = {v["minor"]: v["status"] for v in app.cluster_versions(None, None)["versions"]}
    assert vs["1.37"] == "unverified" and "1.38" not in vs


def test_component_versions(ui, monkeypatch):
    from eks_precheck import server as srv
    from eks_precheck.sources.awscli import AwsCliError

    base, s, _ = ui
    # Helm: GitHub Release 태그
    data = s.get(base + "/api/component-versions", params={"name": "vpc-cni", "install": "helm"}).json()
    assert data["source"] == "GitHub Release" and data["versions"][0] == "v1.20.0"
    assert "v1.19.1" not in " ".join(data["versions"])  # prerelease 제외

    # EKS add-on: describe-addon-versions
    def run_json(args, profile=None, region=None, timeout=30):
        assert args[:4] == ["eks", "describe-addon-versions", "--addon-name", "coredns"]
        return {"addons": [{"addonVersions": [
            {"addonVersion": "v1.11.4-eksbuild.2", "compatibilities": [{"clusterVersion": "1.33", "defaultVersion": True}]},
            {"addonVersion": "v1.12.1-eksbuild.1", "compatibilities": [{"clusterVersion": "1.33", "defaultVersion": False}]},
        ]}]}
    monkeypatch.setattr(srv, "run_json", run_json)
    data = s.get(base + "/api/component-versions", params={"name": "coredns", "install": "eks-addon", "k8s": "1.33"}).json()
    assert data["versions"] == ["v1.12.1-eksbuild.1", "v1.11.4-eksbuild.2"] and data["default"] == "v1.11.4-eksbuild.2"

    def fail(*a, **k):
        raise AwsCliError("AWS CLI 가 설치되어 있지 않음")
    monkeypatch.setattr(srv, "run_json", fail)
    data = s.get(base + "/api/component-versions", params={"name": "kube-proxy", "install": "eks-addon", "k8s": "1.33"}).json()
    assert "AWS CLI" in data["error"]  # repo 없는 컴포넌트 → 오류 안내


def test_init_has_titles_and_ami_types(ui):
    base, s, _ = ui
    init = s.get(base + "/api/init").json()
    assert "AL2023_x86_64_STANDARD" in init["ami_types"]
    assert init["components"]["karpenter"]["eks_addon"] is None


def test_page_has_tabs(ui):
    base, s, _ = ui
    html = s.get(base + "/").text
    for anchor in ('href="#/input"', 'href="#/report"', 'href="#/history"', 'id="toc"', "function buildPages"):
        assert anchor in html
