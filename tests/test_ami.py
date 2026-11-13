import pytest

from eks_precheck import precheck
from eks_precheck.models import CRITICAL, REVIEW, NodeGroup
from eks_precheck.report import render
from eks_precheck.sources import ami


@pytest.mark.parametrize("ami_type, path", [
    ("AL2023_x86_64_STANDARD", "/aws/service/eks/optimized-ami/1.34/amazon-linux-2023/x86_64/standard/recommended"),
    ("AL2_ARM_64", "/aws/service/eks/optimized-ami/1.34/amazon-linux-2-arm64/recommended"),
    ("BOTTLEROCKET_x86_64_NVIDIA", "/aws/service/bottlerocket/aws-k8s-1.34-nvidia/x86_64/latest"),
    ("WINDOWS_CORE_2022_x86_64", "/aws/service/ami-windows-latest/Windows_Server-2022-English-Core-EKS_Optimized-1.34"),
])
def test_parameter_paths(ami_type, path):
    assert ami.parameter_base(ami_type, "1.34")[0] == path
    assert ami.parameter_base("CUSTOM", "1.34") is None


def _fake_ssm(monkeypatch, table):
    calls = []

    def run_json(args, profile=None, region=None, timeout=30):
        calls.append((args, region))
        names = args[args.index("--names") + 1:]
        return {"Parameters": [{"Name": n, "Value": table[n]} for n in names if n in table],
                "InvalidParameters": [n for n in names if n not in table]}

    monkeypatch.setattr(ami, "run_json", run_json)
    monkeypatch.setattr(ami, "default_region", lambda profile: "ap-northeast-2")
    return calls


AL = "/aws/service/eks/optimized-ami/{v}/amazon-linux-2023/x86_64/standard/recommended/"
SSM = {
    AL.format(v="1.33") + "image_id": "ami-0aaa133",
    AL.format(v="1.33") + "release_version": "1.33.5-20261101",
    AL.format(v="1.34") + "image_id": "ami-0bbb134",
    AL.format(v="1.34") + "release_version": "1.34.2-20261101",
    AL.format(v="1.34") + "image_name": "amazon-eks-node-al2023-x86_64-standard-1.34-v20261101",
}


def test_lookup_and_cache(monkeypatch):
    calls = _fake_ssm(monkeypatch, SSM)
    lk = ami.AmiLookup()
    info = lk.get("AL2023_x86_64_STANDARD", "1.34")
    assert (info.image_id, info.release_version, info.region) == ("ami-0bbb134", "1.34.2-20261101", "ap-northeast-2")
    assert "--region ap-northeast-2" in info.command
    lk.get("AL2023_x86_64_STANDARD", "1.34")
    assert len(calls) == 1  # 캐시
    missing = lk.get("AL2023_x86_64_STANDARD", "1.35")
    assert missing.extra.get("missing") and "AMI 가 없습니다" in missing.error


def test_ami_in_report(monkeypatch, fake_http):
    _fake_ssm(monkeypatch, SSM)
    ngs = [NodeGroup("app", "1.33", "AL2023_x86_64_STANDARD", ami_id="ami-0old"),
           NodeGroup("legacy", "1.33", "AL2_x86_64")]
    report = precheck.run(fake_http({}), {}, "1.33", "1.34", nodegroups=ngs)
    assert report.amis["app"]["target"].image_id == "ami-0bbb134"
    texts = {f.severity: [] for f in report.env_findings}
    for f in report.env_findings:
        texts[f.severity].append(f.text)
    assert any("ami-0old" in t and "ami-0aaa133" in t for t in texts[REVIEW])
    # legacy(AL2) 1.34 AMI 없음은 AL2 지원 종료 항목으로 이미 안내되므로 중복 표시하지 않음
    assert sum("legacy" in t for t in texts[CRITICAL]) == 1
    md = render(report)
    assert "| app | AL2023_x86_64_STANDARD | `ami-0old` | `ami-0aaa133` (1.33) · 1.33.5-20261101 | `ami-0bbb134` (1.34) · 1.34.2-20261101 |" in md
    assert "리전 `ap-northeast-2`" in md


def test_ami_lookup_failure_shows_command(monkeypatch, fake_http):
    def fail(*a, **k):
        raise ami.AwsCliError("AWS CLI 가 설치되어 있지 않음")
    monkeypatch.setattr(ami, "run_json", fail)
    monkeypatch.setattr(ami, "default_region", lambda profile: None)
    report = precheck.run(fake_http({}), {}, "1.33", "1.34", nodegroups=[NodeGroup("app", "1.33", "AL2023_x86_64_STANDARD")])
    md = render(report)
    assert "aws ssm get-parameter --name /aws/service/eks/optimized-ami/1.34/amazon-linux-2023/x86_64/standard/recommended/image_id" in md
    assert "AWS CLI 가 설치되어 있지 않음" in md
