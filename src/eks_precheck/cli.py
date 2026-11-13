"""eks-precheck CLI.

  eks-precheck init                 # 입력 템플릿(env.yaml) 생성
  eks-precheck run env.yaml         # 입력한 환경 기준 영향도 리포트 생성
  eks-precheck cluster --cluster X --to 1.33   # (고급) 클러스터 read-only 조회
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import __version__, config, envfile, precheck, versions
from .http import DEFAULT_CACHE_DIR, HttpClient
from .report import render
from .sources.github import resolve_token

EPILOG = """\
처음 사용 순서:
  1) eks-precheck init              → env.yaml 생성
  2) env.yaml 에 현재/목표 버전과 add-on 버전 입력
  3) eks-precheck run env.yaml      → reports/ 아래 리포트 생성
"""


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-o", "--output", help="리포트 파일 경로 (기본: reports/<날짜>-<from>-to-<to>.md, '-' 는 화면 출력)")
    p.add_argument("--no-issues", action="store_true", help="GitHub 이슈 검색 생략 (더 빠름)")
    p.add_argument("--no-cache", action="store_true", help="캐시(6시간) 사용 안 함")
    p.add_argument("--max-items", type=int, default=20, help="섹션당 표시할 최대 항목 수 (기본 20)")
    p.add_argument("--config", help="컴포넌트 정의 파일 (기본: 내장 components.yaml)")
    p.add_argument("-q", "--quiet", action="store_true", help="진행 로그 출력 안 함")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eks-precheck",
        description="입력한 EKS 버전 / add-on 버전 기준으로 업그레이드 영향도 리포트를 만듭니다.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    s = sub.add_parser("init", help="입력 템플릿(env.yaml) 생성")
    s.add_argument("path", nargs="?", default="env.yaml", help="생성할 파일 (기본: env.yaml)")
    s.add_argument("--force", action="store_true", help="이미 있으면 덮어쓰기")

    s = sub.add_parser("run", help="입력 파일 기준 영향도 리포트 생성")
    s.add_argument("input", help="입력 파일 (예: env.yaml)")
    _add_common(s)

    s = sub.add_parser("cluster", help="(고급) 실제 클러스터를 read-only 로 조회해서 리포트 생성")
    s.add_argument("--cluster", required=True, help="EKS 클러스터 이름")
    s.add_argument("--to", dest="to_minor", required=True, help="목표 Kubernetes 버전 (예: 1.33)")
    s.add_argument("--region", help="AWS 리전 (기본: AWS_REGION / profile 설정)")
    s.add_argument("--profile", help="AWS CLI profile")
    s.add_argument("--kube-context", help="self-managed 컴포넌트 버전 탐지에 쓸 kubectl context")
    s.add_argument("--components", help="분석할 컴포넌트 (쉼표 구분, 기본: 전체)")
    _add_common(s)
    return p


def _init(args, log) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"오류: {path} 가 이미 있습니다. 덮어쓰려면 --force", file=sys.stderr)
        return 1
    path.write_text(envfile.template_text(), encoding="utf-8")
    log(f"생성: {path}\n다음 단계: {path} 를 열어 버전을 고친 뒤 → eks-precheck run {path}")
    return 0


def _http(args, log) -> HttpClient:
    token = resolve_token()
    if not token:
        log("! GITHUB_TOKEN 이 없습니다. GitHub API 제한(시간당 60회)에 걸릴 수 있습니다. "
            "`export GITHUB_TOKEN=$(gh auth token)` 를 권장합니다.")
    return HttpClient(cache_dir=None if args.no_cache else DEFAULT_CACHE_DIR, github_token=token)


def _write(report, args, suffix: str, log) -> None:
    text = render(report, limit=args.max_items)
    if args.output == "-":
        sys.stdout.write(text)
    else:
        out = Path(args.output or f"reports/{dt.date.today():%Y%m%d}-{report.from_minor}-to-{report.to_minor}{suffix}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        log(f"\n리포트 생성: {out}")
    for w in report.warnings:
        log(f"! {w}")


def _run(args, log) -> int:
    try:
        env = envfile.load(args.input, config.load_components(args.config))
    except (ValueError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    log(f"입력: {env.current} → {env.target}, add-on {len(env.components)}개, 노드그룹 {len(env.nodegroups)}개")
    report = precheck.run(
        _http(args, log),
        env.components,
        env.current,
        env.target,
        cli_current=env.current_versions,
        cli_target=env.target_versions,
        search_issues=not args.no_issues,
        nodegroups=env.nodegroups,
        source=str(args.input),
        log=log,
    )
    _write(report, args, f"-{Path(args.input).stem}" if Path(args.input).stem != "env" else "", log)
    return 0


def _cluster(args, log) -> int:
    from .cluster import ClusterError, collect

    try:
        to_minor = versions.minor_str(versions.parse_minor(args.to_minor))
        components = config.select(config.load_components(args.config), args.components)
    except (ValueError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    log(f"[0/2] 클러스터 {args.cluster} 조회 (read-only)")
    try:
        state, warnings = collect(args.cluster, args.region, args.profile, to_minor, components, args.kube_context)
        report = precheck.run(
            _http(args, log), components, None, to_minor,
            cluster=state, cluster_warnings=warnings, search_issues=not args.no_issues, log=log,
        )
    except (ClusterError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    _write(report, args, f"-{args.cluster}", log)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    log = (lambda _m: None) if getattr(args, "quiet", False) else (lambda m: print(m, file=sys.stderr))
    return {"init": _init, "run": _run, "cluster": _cluster}[args.command](args, log)
