import json
import subprocess

from eks_precheck.sources import eks_versions


def test_from_aws_cli_parses_response(monkeypatch):
    # conftest 의 차단을 풀고 실제 함수를 subprocess 수준에서 테스트
    monkeypatch.undo()
    payload = {"clusterVersions": [
        {"clusterVersion": "1.37", "versionStatus": "STANDARD_SUPPORT", "releaseDate": "2026-10-20T00:00:00+00:00"},
        {"clusterVersion": "1.31", "status": "extended-support", "endOfExtendedSupportDate": "2026-11-26T00:00:00Z"},
    ]}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(eks_versions.shutil, "which", lambda name: "/usr/bin/aws")
    monkeypatch.setattr(eks_versions.subprocess, "run", fake_run)
    info, err = eks_versions.from_aws_cli(profile="ro", region="ap-northeast-2")
    assert err == ""
    assert info.versions == {"1.37": "STANDARD_SUPPORT", "1.31": "EXTENDED_SUPPORT"}
    assert info.details["1.37"] == {"releaseDate": "2026-10-20"}
    assert calls[0][1:3] == ["eks", "describe-cluster-versions"] and "--profile" in calls[0]


def test_from_aws_cli_errors(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(eks_versions.shutil, "which", lambda name: None)
    assert eks_versions.from_aws_cli() == (None, "AWS CLI 가 설치되어 있지 않음")

    monkeypatch.setattr(eks_versions.shutil, "which", lambda name: "aws")
    monkeypatch.setattr(eks_versions.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 255, stdout="", stderr="\nUnable to locate credentials. You can configure credentials by running \"aws configure\"."))
    info, err = eks_versions.from_aws_cli()
    assert info is None and "Unable to locate credentials" in err
