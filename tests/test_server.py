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
