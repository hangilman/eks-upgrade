# eks-precheck

**내 EKS 버전과 add-on 버전을 적으면, 업그레이드 영향도를 정리한 리포트를 만들어 주는 로컬 CLI** 입니다.
Kubernetes CHANGELOG, EKS 릴리스 노트, 각 add-on 의 GitHub Release 를 하나씩 열어 보던 사전 조사를 대신합니다.

```
env.yaml (내 환경)  ──▶  eks-precheck run env.yaml  ──▶  reports/20261113-1.31-to-1.33.md
```

Windows / Linux(macOS 포함) 모두 지원합니다. **설치와 실행 명령만 OS 별로 다르고, `env.yaml` 작성법과 리포트는 같습니다.**

| 단계 | Windows | Linux / macOS |
|---|---|---|
| 1. 설치 (최초 1회) | [Windows 설치](#1-설치-windows) | [Linux 설치](#1-설치-linux--macos) |
| 2. 실행 (매번) | [Windows 실행](#2-실행-windows) | [Linux 실행](#2-실행-linux--macos) |
| 3. env.yaml 작성 | [공통](#3-envyaml-작성-공통) | [공통](#3-envyaml-작성-공통) |

---

## Windows

> 모든 명령은 **PowerShell** 기준입니다. (시작 메뉴 → "Terminal" 또는 "PowerShell")

### 1. 설치 (Windows)

**① 준비물 설치** — 이미 있으면 건너뜁니다. 설치 후에는 PowerShell 을 **새로 열어야** 명령이 인식됩니다.

```powershell
winget install -e --id Python.Python.3.12
```

```powershell
winget install -e --id Git.Git
```

```powershell
winget install -e --id GitHub.cli
```

> python.org 설치 파일을 쓸 경우 첫 화면에서 **"Add python.exe to PATH"** 를 체크하세요.

**② 코드 받기 & 설치**

```powershell
git clone https://github.com/hangilman/eks-upgrade.git
```

```powershell
cd eks-upgrade
```

```powershell
.\setup.cmd
```

`setup.cmd` 가 가상환경(`.venv`) 생성과 설치를 한 번에 합니다. `.cmd` 파일은 PowerShell 실행 정책(Execution Policy)의 제한을 받지 않으므로 **`Activate.ps1` 을 쓸 필요가 없습니다.**

**③ GitHub 로그인** (최초 1회, 브라우저가 열림)

```powershell
gh auth login
```

로그인해 두면 도구가 `gh auth token` 으로 토큰을 자동으로 가져오므로 토큰을 직접 넣을 필요가 없습니다.

설치 확인: `.\eks-precheck.cmd --help` 가 사용법을 보여주면 성공입니다.

### 2. 실행 (Windows)

`eks-upgrade` 폴더에서:

```powershell
.\eks-precheck.cmd init
```

```powershell
notepad env.yaml
```

```powershell
.\eks-precheck.cmd run env.yaml
```

<details>
<summary>Activate.ps1 로 가상환경을 활성화해서 쓰고 싶다면</summary>

"이 시스템에서 스크립트를 실행할 수 없으므로…" 오류가 나면, 현재 창에서만 정책을 풀고 활성화합니다 (창을 닫으면 원복됨).

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```powershell
.\.venv\Scripts\Activate.ps1
```

이후에는 `eks-precheck run env.yaml` 처럼 `.cmd` 없이 실행할 수 있습니다. 회사 정책(GPO)으로 막혀 있으면 `.\eks-precheck.cmd` 를 쓰세요.
</details>

리포트 열기 (VS Code 의 Markdown 미리보기 `Ctrl+Shift+V` 로 보면 가장 읽기 좋습니다):

```powershell
code .\reports\
```

> ⚠️ Windows 에서는 `.\eks-precheck.cmd run env.yaml -o - > report.md` 처럼 **`>` 리다이렉트를 쓰지 마세요.** PowerShell 이 인코딩을 바꿔 한글/이모지가 깨집니다. 기본 저장(`reports\`) 또는 `-o report.md` 를 쓰세요.

내 add-on 버전 확인 (AWS CLI / kubectl 이 설정되어 있을 때):

```powershell
aws eks describe-addon --cluster-name <클러스터> --addon-name vpc-cni --query addon.addonVersion --output text
```

```powershell
(kubectl get deploy -A -o jsonpath='{..image}') -split ' ' | Select-String 'karpenter|load-balancer'
```

---

## Linux / macOS

### 1. 설치 (Linux / macOS)

**① 준비물** — Python 3.10 이상, git, (권장) GitHub CLI `gh`

```bash
python3 --version
```

없으면 설치합니다. (Ubuntu: `sudo apt install python3 python3-venv git gh`, Amazon Linux: `sudo dnf install python3 git`, macOS: `brew install python git gh`)

**② 코드 받기 & 설치**

```bash
git clone https://github.com/hangilman/eks-upgrade.git
```

```bash
cd eks-upgrade
```

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -e .
```

**③ GitHub 로그인** (최초 1회)

```bash
gh auth login
```

설치 확인: `eks-precheck --help` 가 사용법을 보여주면 성공입니다.

### 2. 실행 (Linux / macOS)

새 터미널을 열 때마다:

```bash
cd eks-upgrade
```

```bash
source .venv/bin/activate
```

```bash
export GITHUB_TOKEN=$(gh auth token)
```

입력 파일 만들기 → 편집 → 실행:

```bash
eks-precheck init
```

```bash
vi env.yaml
```

```bash
eks-precheck run env.yaml
```

리포트는 `reports/` 에 생성됩니다. 터미널에서 바로 보려면 `-o -` 를 붙이세요.

```bash
eks-precheck run env.yaml -o - | less
```

내 add-on 버전 확인 (AWS CLI / kubectl 이 설정되어 있을 때):

```bash
aws eks describe-addon --cluster-name <클러스터> --addon-name vpc-cni --query addon.addonVersion --output text
```

```bash
kubectl get deploy -A -o jsonpath='{..image}' | tr ' ' '\n' | grep -E 'karpenter|load-balancer'
```

---

## 3. env.yaml 작성 (공통)

`eks-precheck init` 으로 만든 `env.yaml` 에 **현재/목표 버전과 사용 중인 add-on 버전**을 적습니다. **적은 것만 분석합니다.**

```yaml
cluster:
  current: "1.31"     # 현재 EKS 버전
  target: "1.33"      # 목표 버전

addons:
  vpc-cni: "v1.18.3-eksbuild.1"
  coredns: "v1.11.1-eksbuild.9"
  kube-proxy: "v1.31.0-eksbuild.2"
  karpenter: "v1.0.6"

nodegroups:            # (선택) AMI 타입 / 버전 차이 점검
  - name: app
    version: "1.31"
    ami_type: AL2_x86_64
```

- 버전은 **꼭 따옴표로** 감싸세요. (`1.30` 을 그냥 쓰면 YAML 이 `1.3` 으로 읽습니다)
- 들여쓰기는 **스페이스 2칸** (Tab 문자 사용 불가)
- 기본 지원 add-on: `vpc-cni`, `coredns`, `kube-proxy`, `ebs-csi`, `aws-load-balancer-controller`, `karpenter`
- 파일 인코딩은 UTF-8 권장이지만, Windows 메모장의 ANSI 저장도 읽을 수 있습니다.
- (선택) `aws:` 에 profile / region 을 적으면 해당 AWS CLI 설정으로 EKS 지원 버전을 확인합니다. 생략하면 기본 설정을 씁니다.

목표 add-on 버전 지정 / 목록에 없는 컴포넌트 추가:

```yaml
addons:
  aws-load-balancer-controller:
    current: "v2.8.1"
    target: "v2.11.0"     # 생략하면 최신 릴리스까지 분석
  cert-manager:           # 기본 목록에 없으면 repo 를 함께 적기
    current: "v1.14.4"
    repo: cert-manager/cert-manager
```

환경이 여러 개면 파일을 나눠 두면 됩니다. 예: `eks-precheck run stg.yaml`, `eks-precheck run prd.yaml`
(`env*.yaml` 은 사내 정보 보호를 위해 `.gitignore` 처리되어 있습니다)

### 자주 쓰는 옵션

| 옵션 | 설명 |
|---|---|
| `--no-issues` | GitHub 이슈 검색 생략 (더 빠름) |
| `-o 파일.md` | 리포트 저장 경로 지정 |
| `--no-cache` | 캐시(6시간) 무시하고 새로 수집 |

---

## 리포트에 담기는 내용

| 섹션 | 내용 |
|---|---|
| 요약 · 컴포넌트별 영향도 | 🔴 필수 조치 / 🟡 검토 / 🔒 보안 / 🐛 이슈 건수, add-on 별 `현재 → 목표` |
| EKS 지원 상태 | 경로상 각 버전이 EKS 에서 standard / extended / 미지원 / 지원 종료인지. 목표 버전이 미지원이면 맨 위에 🔴 표시 |
| 노드그룹 점검 | AL2 AMI 지원 종료(1.33+), kubelet 버전 차이(skew) |
| Kubernetes / EKS 변경사항 | 경로상 각 버전(예: 1.32, 1.33)의 제거 API, EKS 중요 공지, Urgent Upgrade Notes, Deprecation |
| Add-on | 현재~목표 사이 릴리스의 Breaking / 보안 / Deprecation 항목, 관련 오픈 이슈, 호환 버전 확인 명령 |
| 체크리스트 | 업그레이드 전 확인 항목, 롤백 시 주의점 |

데이터 출처: [Kubernetes Deprecation Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/),
[EKS User Guide](https://github.com/awsdocs/amazon-eks-user-guide), `kubernetes/kubernetes` CHANGELOG, 각 add-on GitHub Release/Issue.
버전별 내용은 실행할 때마다 원문에서 가져오므로 새 버전이 나와도 도구를 고칠 필요가 없습니다.

### EKS 지원 버전은 어떻게 확인하나

EKS 는 업스트림 Kubernetes 보다 늦게 새 버전을 출시하므로, 목표 버전이 EKS 에서 지원되는지 아래 순서로 확인합니다.

1. **AWS API** — `aws eks describe-cluster-versions` (AWS CLI 가 설치·로그인되어 있을 때, 읽기 전용). 가장 정확합니다.
2. **AWS 문서 사이트** — docs.aws.amazon.com 의 EKS 버전 페이지
3. 둘 다 실패하면 GitHub 문서 원본만 참고하되, **원본은 갱신이 수개월 늦을 수 있어 "미지원"으로 단정하지 않고 🟡 "확인 필요"로 표시**합니다.

AWS CLI 확인이 필요 없으면 `--no-aws` 를 붙이세요. 필요한 IAM 권한은 `eks:DescribeClusterVersions` (읽기 전용) 하나입니다.

## 한계
- 분류는 키워드 기반이라 오분류·누락이 있을 수 있습니다. 최종 판단은 리포트의 원문 링크로 하세요.
- 입력한 값만 분석합니다. 매니페스트 안의 deprecated API 사용 여부는 `pluto` / `kubent` 또는 EKS 콘솔의 Upgrade Insights 로 확인하세요.
- EKS 전용 변경사항(릴리스 노트 본문)은 GitHub 문서 원본에서 추출하므로, 최신 EKS 버전은 원본 갱신 전까지 비어 있을 수 있습니다. 이 경우 리포트에 AWS 문서 링크로 직접 확인하라고 표시됩니다.

## 문제 해결

| 증상 | Windows | Linux / macOS |
|---|---|---|
| `스크립트를 실행할 수 없으므로…` (Activate.ps1) | `.\eks-precheck.cmd` 사용 (활성화 불필요) | - |
| `eks-precheck` 명령을 찾을 수 없음 | `.\eks-precheck.cmd` 로 실행 (없으면 `.\setup.cmd` 먼저) | `source .venv/bin/activate` 실행 여부 확인 |
| `python`/`py`/`git` 명령을 찾을 수 없음 | 설치 후 PowerShell 을 새로 열기 | 패키지 설치 확인 |
| `rate limit 초과` | `gh auth login` 확인 또는 `$env:GITHUB_TOKEN = gh auth token` 후 재실행 | `export GITHUB_TOKEN=$(gh auth token)` 후 재실행 |
| 회사 프록시/SSL 오류 (`SSLError`, `CERTIFICATE_VERIFY_FAILED`) | `$env:HTTPS_PROXY = "http://프록시:포트"`, 사내 CA 는 `$env:REQUESTS_CA_BUNDLE = "C:\경로\ca.pem"` | `export HTTPS_PROXY=...`, `export REQUESTS_CA_BUNDLE=/경로/ca.pem` |
| `버전 ... 을 따옴표로 감싸 주세요` | `env.yaml` 의 버전을 `"1.30"` 처럼 따옴표로 | 동일 |
| `알 수 없는 컴포넌트` | 해당 add-on 아래에 `repo: owner/name` 추가 | 동일 |

결과는 캐시됩니다 (Windows: `%LOCALAPPDATA%\eks-precheck\cache`, Linux/macOS: `~/.cache/eks-precheck`). 이상하면 `--no-cache` 로 다시 실행하세요.

---

## (고급) 클러스터 직접 조회

입력 파일 대신 실제 클러스터를 read-only 로 조회해 버전, add-on 호환성, Upgrade Insights 를 자동으로 채울 수도 있습니다. AWS CLI 자격증명(profile)이 설정되어 있어야 합니다.

```powershell
pip install -e ".[cluster]"
```

```powershell
eks-precheck cluster --cluster my-cluster --region ap-northeast-2 --profile readonly --to 1.33
```

(Linux/macOS 도 명령은 동일합니다.)

필요 IAM 권한 (읽기 전용): `eks:DescribeCluster`, `eks:ListAddons`, `eks:DescribeAddon`, `eks:DescribeAddonVersions`,
`eks:ListNodegroups`, `eks:DescribeNodegroup`, `eks:ListInsights`, `eks:DescribeInsight`.
쓰기 API 는 호출하지 않습니다.

## 개발

```bash
pip install -e ".[dev,cluster]"
```

```bash
pytest
```
