"""eks-precheck CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import __version__, config, precheck, versions
from .http import DEFAULT_CACHE_DIR, HttpClient
from .report import render
from .sources.github import resolve_token

EPILOG = """\
예시:
  # 오프라인: 버전만 지정
  eks-precheck --from 1.29 --to 1.31

  # 현재 add-on 버전을 알려주면 그 사이 릴리스만 분석
  eks-precheck --from 1.30 --to 1.31 --current vpc-cni=v1.18.3 --current coredns=v1.11.1

  # 클러스터 read-only 조회 (pip install -e '.[cluster]' 필요)
  eks-precheck --cluster my-cluster --region ap-northeast-2 --to 1.31
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eks-precheck",
        description="EKS 업그레이드 전 Kubernetes/EKS/Add-on 변경사항과 이슈를 모아 Markdown 리포트를 생성합니다.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--from", dest="from_minor", help="현재 Kubernetes 버전 (예: 1.29). --cluster 사용 시 생략 가능")
    p.add_argument("--to", dest="to_minor", required=True, help="목표 Kubernetes 버전 (예: 1.31)")
    p.add_argument("--components", help="분석할 컴포넌트 (쉼표 구분). 기본: 설정 파일의 전체")
    p.add_argument("--config", help="components.yaml 경로 (기본: 내장 설정)")
    p.add_argument("--current", action="append", metavar="NAME=VER", help="컴포넌트 현재 버전 (반복 가능)")
    p.add_argument("--target", action="append", metavar="NAME=VER", help="컴포넌트 목표 버전 (반복 가능, 기본: 최신 또는 EKS 기본 버전)")

    g = p.add_argument_group("클러스터 조회 (read-only)")
    g.add_argument("--cluster", help="EKS 클러스터 이름")
    g.add_argument("--region", help="AWS 리전 (기본: AWS_REGION / profile 설정)")
    g.add_argument("--profile", help="AWS CLI profile")
    g.add_argument("--kube-context", help="self-managed 컴포넌트 버전 탐지에 쓸 kubectl context")

    o = p.add_argument_group("출력/수집 옵션")
    o.add_argument("-o", "--output", help="리포트 파일 경로 (기본: reports/<날짜>-<from>-to-<to>.md, '-' 는 stdout)")
    o.add_argument("--no-issues", action="store_true", help="GitHub 이슈 검색 생략")
    o.add_argument("--no-cache", action="store_true", help="캐시 사용 안 함")
    o.add_argument("--lookback", type=int, default=5, help="현재 버전을 모를 때 분석할 최근 릴리스 수 (기본 5)")
    o.add_argument("--max-items", type=int, default=20, help="섹션당 표시할 최대 항목 수 (기본 20)")
    o.add_argument("-q", "--quiet", action="store_true", help="진행 로그 출력 안 함")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda _m: None) if args.quiet else (lambda m: print(m, file=sys.stderr))

    try:
        to_minor = versions.minor_str(versions.parse_minor(args.to_minor))
        components = config.select(config.load_components(args.config), args.components)
        cli_current = precheck.parse_kv(args.current, "--current")
        cli_target = precheck.parse_kv(args.target, "--target")
    except (ValueError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    token = resolve_token()
    if not token:
        log("! GITHUB_TOKEN 이 없습니다. GitHub API 제한(시간당 60회)에 걸릴 수 있습니다. "
            "`export GITHUB_TOKEN=$(gh auth token)` 를 권장합니다.")
    http = HttpClient(cache_dir=None if args.no_cache else DEFAULT_CACHE_DIR, github_token=token)

    cluster_state, cluster_warnings = None, []
    if args.cluster:
        from .cluster import ClusterError, collect

        log(f"[0/2] 클러스터 {args.cluster} 조회 (read-only)")
        try:
            cluster_state, cluster_warnings = collect(
                args.cluster, args.region, args.profile, to_minor, components, args.kube_context
            )
        except (ClusterError, ValueError) as e:
            print(f"오류: {e}", file=sys.stderr)
            return 1

    try:
        report = precheck.run(
            http,
            components,
            args.from_minor,
            to_minor,
            cluster=cluster_state,
            cluster_warnings=cluster_warnings,
            cli_current=cli_current,
            cli_target=cli_target,
            search_issues=not args.no_issues,
            lookback=args.lookback,
            log=log,
        )
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    text = render(report, limit=args.max_items)
    if args.output == "-":
        sys.stdout.write(text)
    else:
        suffix = f"-{args.cluster}" if args.cluster else ""
        out = Path(args.output or f"reports/{dt.date.today():%Y%m%d}-{report.from_minor}-to-{report.to_minor}{suffix}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        log(f"리포트 생성: {out}")
    for w in report.warnings:
        log(f"! {w}")
    return 0
