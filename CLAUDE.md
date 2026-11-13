# CLAUDE.md

## 프로젝트 목적
EKS 업그레이드 전 사전 조사(Release note, CHANGELOG, 이슈 확인)를 자동화하는 **로컬 CLI** (`eks-precheck`).
정기 실행이 아니라 업그레이드 계획 시점에 사람이 직접 실행하고 리포트를 검토하는 용도이다. GitHub Actions 는 현재 범위 밖이다.

## 사용 흐름 (기본)
- 웹 UI (권장): `eks-precheck ui` → 127.0.0.1 로컬 서버 + 브라우저에서 입력/리포트 확인
- CLI: `eks-precheck init` → 사용자가 `env.yaml` 에 현재/목표 버전, add-on 버전 입력 → `eks-precheck run env.yaml`
**입력한 컴포넌트만 분석**하는 것이 기본 동작이다. `eks-precheck cluster` (boto3 조회)는 고급 옵션이다.

## 구조
- `src/eks_precheck/cli.py`: argparse 진입점 (`init` / `run` / `cluster` 서브커맨드)
- `envfile.py`: 입력 파일(env.yaml)/웹 입력(dict) 검증 (`from_dict`), 템플릿은 `data/env-template.yaml`
- `server.py`: 웹 UI 서버 (stdlib `http.server`, 127.0.0.1 전용, Host/Origin 검사), 화면은 `data/ui.html` (외부 CDN 없이 단일 파일)
  - 화면은 해시 라우팅 탭: `#/input` (입력), `#/report/<파일>/<항목>` (리포트를 h2/h3 기준 항목 화면으로 분할, 왼쪽 메뉴), `#/history` (지난 리포트)
  - 리포트 항목 분할은 브라우저에서 리포트 HTML 의 h2/h3 로 한다. 리포트 Markdown 제목 구조(`## 요약`, `## N. ...변경사항`, `## N. Add-on / 컴포넌트`, `### ...`)를 바꾸면 `buildPages()` 도 함께 확인한다.
- `md_render.py`: 리포트 Markdown → HTML (모든 HTML escape, http(s) 링크만 허용)
- `precheck.py`: 수집 → 분석 → `models.Report` 생성 (오케스트레이션)
- `sources/`: 외부 원문 수집/파싱 (`k8s.py` CHANGELOG·Deprecation Guide, `eks_docs.py` EKS User Guide adoc, `eks_versions.py` EKS 지원 버전, `ami.py` 권장 AMI(SSM 공개 파라미터), `awscli.py` AWS CLI 호출, `github.py` Release/Issue)
- `classify.py`: Release note 항목의 규칙 기반 분류 (critical / security / review / info)
- `cluster.py`: `--cluster` 모드, boto3 read-only 조회
- `report.py`: Markdown 렌더링 (한국어)
- `data/components.yaml`: 추적 컴포넌트 정의 (EKS add-on 가능 여부 `eks_addon`, Helm 전용, `tag_prefix`, `follows_k8s_minor`)

## 원칙
- 버전별 사실(제거 API, EKS 공지 등)은 코드에 하드코딩하지 않고 **원문에서 매번 추출**한다. 예외는 `precheck.py` 의 상수(kubelet skew, AL2 마지막 버전)뿐이며 출처를 주석으로 남긴다.
- EKS 지원 여부(미지원/지원 종료)는 **공식 출처(AWS API `describe-cluster-versions`, AWS 문서 사이트)로만 단정**한다. GitHub 문서 원본(awsdocs)은 갱신이 수개월 늦을 수 있으므로 릴리스 노트 본문 추출에만 쓰고, 원본에 없다는 이유로 "미지원"이라 판단하지 않는다.
- AWS 호출은 AWS CLI 의 **read-only 명령만** 사용한다 (`describe-*`, `list-*`, `ssm get-parameters`). AWS CLI 가 없거나 실패하면 건너뛰고 직접 확인할 명령을 리포트에 안내한다.
- 클러스터 조회는 **read-only API 만** 사용한다. 쓰기 API 를 추가하지 않는다.
- 외부 수집 실패는 예외로 중단하지 않고 `report.warnings` 에 기록한 뒤 계속 진행한다.
- 리포트 문구는 한국어, 기술 용어/명령어는 영어 원문 유지.
- Windows / Linux 모두 지원한다. 파일 IO 는 항상 `encoding=` 을 명시하고, 사용자 파일은 `textio.read_user_text` 로 읽는다. 셸 명령 예시는 OS 별로 나누거나 양쪽에서 동작하는 한 줄로 쓴다.
- 웹 UI 는 추가 의존성 없이 유지한다 (서버는 표준 라이브러리, 화면은 외부 CDN 없는 단일 HTML). 사내망/폐쇄망에서도 동작해야 한다.
- 테스트는 네트워크 없이 `tests/fixtures/` 와 `FakeHttp`, 가짜 EKS client 로 작성한다.

## 명령
- 테스트: `pytest` (인코딩 누락 점검: `python -X warn_default_encoding -W error::EncodingWarning -m pytest`)
- 실행 예: `eks-precheck init && eks-precheck run env.yaml --no-issues -o -`
