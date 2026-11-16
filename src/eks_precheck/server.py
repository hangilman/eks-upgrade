"""로컬 웹 UI 서버 (`eks-precheck ui`).

- 표준 라이브러리 http.server 만 사용 (추가 설치 없음)
- 127.0.0.1 에만 바인딩하고 Host / Origin 을 검사해 다른 사이트에서의 요청을 거부
- 리포트 생성은 백그라운드 스레드에서 실행하고, 브라우저가 진행 로그를 폴링
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import uuid
import webbrowser
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, config, envfile, precheck, troubleshoot, versions
from .http import DEFAULT_CACHE_DIR, FetchError, HttpClient
from .md_render import render_html
from .report import render
from .sources import eks_docs, eks_versions, k8s
from .sources.ami import AMI_TYPES
from .sources.awscli import AwsCliError, run_json
from .sources.github import DEFAULT_TAG_PATTERN, GitHub, resolve_token, versioned

REPORT_NAME = re.compile(r"^[\w.-]+\.md$")
MAX_BODY = 256 * 1024


def _default_http_factory(no_cache: bool) -> HttpClient:
    return HttpClient(cache_dir=None if no_cache else DEFAULT_CACHE_DIR, github_token=resolve_token())


class App:
    def __init__(
        self,
        workdir: Path,
        config_path: str | None = None,
        http_factory: Callable[[bool], object] = _default_http_factory,
    ):
        self.workdir = workdir
        self.reports_dir = workdir / "reports"
        self.known = config.load_components(config_path)
        self.http_factory = http_factory
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self._cache: dict[tuple, dict] = {}

    # ---- 초기 데이터 ----
    def init_payload(self) -> dict:
        env, env_error = None, None
        env_path = self.workdir / "env.yaml"
        if env_path.exists():
            try:
                env = envfile.load_raw(env_path)
            except envfile.InputError as e:
                env_error = str(e)
        return {
            "version": __version__,
            "components": {
                name: {"title": spec.get("title") or name, "repo": spec.get("repo"), "eks_addon": spec.get("eks_addon")}
                for name, spec in self.known.items()
            },
            "ami_types": list(AMI_TYPES),
            "env": _jsonable(env),
            "env_error": env_error,
            "github_token": bool(resolve_token()),
            "reports": self.list_reports(),
        }

    # ---- 선택지 ----
    def _cached(self, key: tuple, fn: Callable[[], dict]) -> dict:
        with self.lock:
            if key in self._cache:
                return self._cache[key]
        value = fn()
        if not value.get("error"):
            with self.lock:
                self._cache[key] = value
        return value

    def cluster_versions(self, profile: str | None, region: str | None) -> dict:
        return self._cached(("versions", profile, region), lambda: self._cluster_versions(profile, region))

    def _cluster_versions(self, profile, region) -> dict:
        http = self.http_factory(False)
        support = eks_versions.resolve(http, True, profile, region, lambda _m: None)
        status_map = {eks_versions.STANDARD: "standard", eks_versions.EXTENDED: "extended", eks_versions.UNSUPPORTED: "ended"}
        found = {m: status_map[s] for m, s in support.versions.items()}
        source = support.source
        if not found:  # 공식 출처 실패 → GitHub 문서 원본 (확인 필요 표시)
            for raw, _web in eks_docs.DOCS.values():
                try:
                    for mm in eks_docs.available_minors(http.get(raw)):
                        found[versions.minor_str(mm)] = "unverified"
                except FetchError:
                    pass
            if found:  # 문서 원본은 갱신이 늦으므로 업스트림에 정식 출시된 다음 버전도 선택지로 제공
                newest = max(versions.parse_minor(m) for m in found)
                for nxt in range(newest[1] + 1, newest[1] + 4):
                    minor = f"{newest[0]}.{nxt}"
                    try:
                        if not k8s.release_section(http.get(k8s.CHANGELOG_RAW.format(minor=minor)), minor):
                            break
                    except FetchError:
                        break
                    found[minor] = "unverified"
            source = "GitHub 문서 원본 + 업스트림 Kubernetes (EKS 지원 여부 확인 필요)" if found else "기본 목록 (EKS 지원 여부 확인 필요)"
        if not found:
            found = {f"1.{m}": "unverified" for m in range(28, 38)}
        known = sorted((versions.parse_minor(m) for m in found), reverse=True)
        oldest = known[-1]
        for m in range(oldest[1] - 1, max(oldest[1] - 6, 20), -1):  # 지원 종료된 예전 버전도 '현재 버전' 선택용으로 포함
            found.setdefault(f"{oldest[0]}.{m}", "ended")
        items = sorted(found.items(), key=lambda kv: versions.parse_minor(kv[0]), reverse=True)
        return {"source": source, "errors": support.errors,
                "versions": [{"minor": m, "status": s} for m, s in items]}

    def component_versions(self, name: str, install: str, k8s: str | None, profile, region) -> dict:
        spec = self.known.get(name)
        if spec is None:
            return {"versions": [], "source": "", "error": "알 수 없는 컴포넌트"}
        return self._cached(("comp", name, install, k8s, profile, region),
                            lambda: self._component_versions(name, spec, install, k8s, profile, region))

    def _component_versions(self, name, spec, install, k8s, profile, region) -> dict:
        errors = []
        if install == envfile.INSTALL_EKS and spec.get("eks_addon"):
            args = ["eks", "describe-addon-versions", "--addon-name", spec["eks_addon"]]
            if k8s:
                args += ["--kubernetes-version", k8s]
            try:
                data = run_json(args, profile, region, timeout=40)
                vs, default = [], None
                for entry in (data or {}).get("addons", []):
                    for av in entry.get("addonVersions", []):
                        vs.append(av["addonVersion"])
                        if any(c.get("defaultVersion") and (not k8s or c.get("clusterVersion") == k8s)
                               for c in av.get("compatibilities", [])):
                            default = av["addonVersion"]
                vs = sorted(set(vs), key=lambda v: versions.parse(v) or (0, 0, 0), reverse=True)
                return {"versions": vs, "default": default,
                        "source": f"AWS API (describe-addon-versions{', Kubernetes ' + k8s if k8s else ''})"}
            except AwsCliError as e:
                errors.append(str(e))
        repo = spec.get("repo") or spec.get("version_repo")
        if repo:
            try:
                same_minor = spec.get("versions_match_k8s_minor") and k8s
                releases = GitHub(self.http_factory(False)).releases(repo, max_pages=2 if same_minor else 1)
                pairs = versioned(releases, spec.get("tag_pattern", DEFAULT_TAG_PATTERN), spec.get("tag_prefix", ""))
                if same_minor:
                    want = versions.parse_minor(k8s)
                    pairs = [(v, r) for v, r in pairs if v[:2] == want]
                vs = [versions.fmt(v) for v, _ in pairs][::-1][:40]
                source = "GitHub Release"
                if spec.get("version_repo") and not spec.get("repo"):
                    source = (f"Kubernetes {k8s or ''} 업스트림 패치 버전 (EKS add-on 실제 버전에는 -eksbuild.N 이 붙음)"
                              + (f" · AWS CLI 조회 실패: {errors[0]}" if errors else ""))
                return {"versions": vs, "default": None, "source": source, "notes": errors}
            except FetchError as e:
                errors.append(f"GitHub Release 조회 실패: {e}")
        return {"versions": [], "source": "", "error": "; ".join(errors) or "버전 목록을 제공하지 않는 컴포넌트"}

    def list_reports(self) -> list[str]:
        if not self.reports_dir.is_dir():
            return []
        files = sorted(self.reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.name for p in files[:30]]

    def read_report(self, name: str) -> dict | None:
        if not REPORT_NAME.match(name):
            return None
        path = self.reports_dir / name
        if not path.is_file():
            return None
        md = path.read_text(encoding="utf-8")
        return {"name": name, "markdown": md, "html": render_html(md)}

    # ---- 실행 ----
    def start_job(self, payload: dict) -> str:
        env = envfile.from_dict(payload, self.known)  # 잘못된 입력은 InputError 로 즉시 반환
        opts = payload.get("options") or {}
        job_id = uuid.uuid4().hex[:12]
        job = {"status": "running", "logs": [], "error": None, "report": None, "warnings": []}
        with self.lock:
            self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job, env, opts), daemon=True).start()
        return job_id

    def _run(self, job: dict, env: envfile.EnvInput, opts: dict) -> None:
        def log(msg: str) -> None:
            job["logs"].append(msg)

        try:
            log(f"입력: {env.current} → {env.target}, add-on {len(env.components)}개, 노드그룹 {len(env.nodegroups)}개")
            report = precheck.run(
                self.http_factory(bool(opts.get("no_cache"))),
                env.components,
                env.current,
                env.target,
                cli_current=env.current_versions,
                cli_target=env.target_versions,
                search_issues=not opts.get("no_issues"),
                nodegroups=env.nodegroups,
                source="웹 UI 입력",
                use_aws=not opts.get("no_aws"),
                aws_profile=env.aws_profile,
                aws_region=env.aws_region,
                log=log,
            )
            md = render(report)
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            name = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{report.from_minor}-to-{report.to_minor}.md"
            (self.reports_dir / name).write_text(md, encoding="utf-8")
            log(f"리포트 저장: reports/{name}")
            job["warnings"] = report.warnings
            job["report"] = {"name": name, "markdown": md, "html": render_html(md)}
            job["status"] = "done"
        except Exception as e:  # 예상 못한 오류도 화면에 보여준다
            job["error"] = f"{type(e).__name__}: {e}"
            job["status"] = "error"

    def job_state(self, job_id: str) -> dict | None:
        job = self.jobs.get(job_id)
        return None if job is None else dict(job, logs=list(job["logs"]))


def _jsonable(obj):
    """YAML 에서 읽은 값(float 버전 등)을 JSON 으로 보낼 수 있게 문자열화."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    return str(obj)


def make_handler(app: App, port_ref: dict):
    page = resources.files("eks_precheck").joinpath("data/ui.html").read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "eks-precheck"

        def log_message(self, fmt, *args):  # 콘솔을 조용하게
            pass

        def _allowed_host(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            port = port_ref["port"]
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if not self._allowed_host():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "허용되지 않은 Host"})
            path = urlparse(self.path).path
            if path == "/":
                return self._send(HTTPStatus.OK, page.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/init":
                return self._json(HTTPStatus.OK, app.init_payload())
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items() if v and v[0]}
            if path == "/api/troubleshooting":
                return self._json(HTTPStatus.OK, troubleshoot.load())
            if path == "/api/versions":
                return self._json(HTTPStatus.OK, app.cluster_versions(q.get("profile"), q.get("region")))
            if path == "/api/component-versions":
                return self._json(HTTPStatus.OK, app.component_versions(
                    q.get("name", ""), q.get("install", ""), q.get("k8s"), q.get("profile"), q.get("region")))
            if path == "/api/reports":
                return self._json(HTTPStatus.OK, {"reports": app.list_reports()})
            if path.startswith("/api/reports/"):
                data = app.read_report(unquote(path.rsplit("/", 1)[-1]))
                return self._json(HTTPStatus.OK, data) if data else self._json(HTTPStatus.NOT_FOUND, {"error": "리포트 없음"})
            if path.startswith("/api/jobs/"):
                state = app.job_state(path.rsplit("/", 1)[-1])
                return self._json(HTTPStatus.OK, state) if state else self._json(HTTPStatus.NOT_FOUND, {"error": "작업 없음"})
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if not self._allowed_host():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "허용되지 않은 Host"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc.lower() != (self.headers.get("Host") or "").lower():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "허용되지 않은 Origin"})
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON 만 허용"})
            if urlparse(self.path).path != "/api/run":
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "요청 크기가 올바르지 않습니다"})
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("JSON 객체가 아닙니다")
                job_id = app.start_job(payload)
            except envfile.InputError as e:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            except ValueError as e:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": f"잘못된 요청: {e}"})
            self._json(HTTPStatus.ACCEPTED, {"job": job_id})

    return Handler


def create_server(app: App, port: int) -> ThreadingHTTPServer:
    port_ref = {"port": port}
    server = None
    for candidate in ([port] if port == 0 else range(port, port + 10)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), make_handler(app, port_ref))
            break
        except OSError:
            continue
    if server is None:
        raise OSError(f"{port}~{port + 9} 포트를 모두 사용 중입니다. --port 로 다른 포트를 지정하세요.")
    port_ref["port"] = server.server_address[1]
    return server


def serve(port: int, open_browser: bool, config_path: str | None, log) -> int:
    app = App(Path.cwd(), config_path)
    server = create_server(app, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    log(f"eks-precheck UI: {url}")
    log("이 PC 에서만 접속됩니다. 종료하려면 Ctrl+C")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("\n종료합니다.")
    finally:
        server.server_close()
    return 0
