import pytest

from eks_precheck import config, envfile
from eks_precheck.cli import main

KNOWN = config.load_components(None)


def _write(tmp_path, text):
    p = tmp_path / "env.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_template_is_valid_input(tmp_path):
    env = envfile.load(_write(tmp_path, envfile.template_text()), KNOWN)
    assert (env.current, env.target) == ("1.31", "1.33")
    assert list(env.components) == ["vpc-cni", "coredns", "kube-proxy"]  # 입력한 것만
    assert env.current_versions["vpc-cni"] == "v1.18.3-eksbuild.1"
    assert env.nodegroups == []


def test_full_input(tmp_path):
    env = envfile.load(_write(tmp_path, """
cluster: {current: "1.30", target: "1.32"}
addons:
  karpenter: "v1.0.6"
  aws-load-balancer-controller: {current: "v2.8.1", target: "v2.11.0"}
  cert-manager: {current: "v1.14.4", repo: cert-manager/cert-manager}
nodegroups:
  - {name: app, version: "1.30", ami_type: AL2_x86_64}
"""), KNOWN)
    assert env.target_versions == {"aws-load-balancer-controller": "v2.11.0"}
    assert env.components["cert-manager"]["repo"] == "cert-manager/cert-manager"
    assert env.components["karpenter"]["repo"] == "aws/karpenter-provider-aws"  # 기본 정의 병합
    assert env.nodegroups[0].ami_type == "AL2_x86_64"


@pytest.mark.parametrize("text, msg", [
    ('cluster: {current: 1.30, target: "1.31"}', "따옴표"),
    ('cluster: {current: "1.31", target: "1.30"}', "높아야"),
    ('cluster: {current: "1.30", target: "1.31"}\naddons: {istio: "1.22.0"}', "repo"),
    ('cluster: {target: "1.31"}', "cluster.current"),
])
def test_input_errors(tmp_path, text, msg):
    with pytest.raises(envfile.InputError, match=msg):
        envfile.load(_write(tmp_path, text), KNOWN)


def test_missing_file(tmp_path):
    with pytest.raises(envfile.InputError, match="init"):
        envfile.load(tmp_path / "nope.yaml", KNOWN)


def test_cli_init_and_run(tmp_path, monkeypatch, fixture_text, fake_http, capsys):
    from test_precheck import _routes

    from eks_precheck import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "resolve_token", lambda: "t")
    monkeypatch.setattr(cli, "HttpClient", lambda **kw: fake_http(_routes(fixture_text)))

    assert main(["init"]) == 0
    assert main(["init"]) == 1  # 이미 존재
    (tmp_path / "env.yaml").write_text("""
cluster: {current: "1.30", target: "1.31"}
addons:
  vpc-cni: "v1.19.0-eksbuild.1"
nodegroups:
  - {name: legacy, version: "1.27", ami_type: AL2_x86_64}
""", encoding="utf-8")
    assert main(["run", "env.yaml", "-o", "-", "-q"]) == 0
    md = capsys.readouterr().out
    assert "### 컴포넌트별 영향도" in md
    assert "| vpc-cni | v1.19.0-eksbuild.1 → v1.20.0 | 2 | 1 | 1 |" in md
    assert "노드그룹 점검 (입력값 기준)" in md and "`legacy`" in md and "skew" in md
    assert "aws eks describe-addon-versions --addon-name vpc-cni --kubernetes-version 1.31" in md
    assert "coredns" not in md.split("## 2.")[0]  # 입력 안 한 add-on 은 분석하지 않음


@pytest.mark.parametrize("encode", [
    lambda t: t.encode("cp949"),                 # Windows 메모장 ANSI 저장
    lambda t: b"\xef\xbb\xbf" + t.encode("utf-8"),  # UTF-8 BOM
])
def test_windows_saved_files(tmp_path, encode):
    p = tmp_path / "env.yaml"
    p.write_bytes(encode('# 한글 주석\ncluster:\n  current: "1.31"\n  target: "1.32"\n'))
    env = envfile.load(p, KNOWN)
    assert (env.current, env.target) == ("1.31", "1.32")
