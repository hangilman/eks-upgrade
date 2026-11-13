# CLAUDE.md

## 프로젝트 목적
EKS 업그레이드 전 사전 조사(Release note, CHANGELOG, 이슈 확인)를 자동화하는 **로컬 CLI** (`eks-precheck`).
정기 실행이 아니라 업그레이드 계획 시점에 사람이 직접 실행하고 리포트를 검토하는 용도이다. GitHub Actions 는 현재 범위 밖이다.

## 사용 흐름 (기본)
`eks-precheck init` → 사용자가 `env.yaml` 에 현재/목표 버전, add-on 버전 입력 → `eks-precheck run env.yaml`.
**입력한 컴포넌트만 분석**하는 것이 기본 동작이다. `eks-precheck cluster` (boto3 조회)는 고급 옵션이다.

## 구조
- `src/eks_precheck/cli.py`: argparse 진입점 (`init` / `run` / `cluster` 서브커맨드)
- `envfile.py`: 입력 파일(env.yaml) 로드/검증, 템플릿은 `data/env-template.yaml`
- `precheck.py`: 수집 → 분석 → `models.Report` 생성 (오케스트레이션)
- `sources/`: 외부 원문 수집/파싱 (`k8s.py` CHANGELOG·Deprecation Guide, `eks_docs.py` EKS User Guide adoc, `github.py` Release/Issue)
- `classify.py`: Release note 항목의 규칙 기반 분류 (critical / security / review / info)
- `cluster.py`: `--cluster` 모드, boto3 read-only 조회
- `report.py`: Markdown 렌더링 (한국어)
- `data/components.yaml`: 추적 컴포넌트 정의

## 원칙
- 버전별 사실(제거 API, EKS 공지 등)은 코드에 하드코딩하지 않고 **원문에서 매번 추출**한다. 예외는 `precheck.py` 의 상수(kubelet skew, AL2 마지막 버전)뿐이며 출처를 주석으로 남긴다.
- 클러스터 조회는 **read-only API 만** 사용한다. 쓰기 API 를 추가하지 않는다.
- 외부 수집 실패는 예외로 중단하지 않고 `report.warnings` 에 기록한 뒤 계속 진행한다.
- 리포트 문구는 한국어, 기술 용어/명령어는 영어 원문 유지.
- 테스트는 네트워크 없이 `tests/fixtures/` 와 `FakeHttp`, 가짜 EKS client 로 작성한다.

## 명령
- 테스트: `pytest`
- 실행 예: `eks-precheck init && eks-precheck run env.yaml --no-issues -o -`
