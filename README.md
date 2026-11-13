# eks-precheck

**내 EKS 버전과 add-on 버전을 적으면, 업그레이드 영향도를 정리한 리포트를 만들어 주는 로컬 CLI** 입니다.
Kubernetes CHANGELOG, EKS 릴리스 노트, 각 add-on 의 GitHub Release 를 하나씩 열어 보던 사전 조사를 대신합니다.

```
env.yaml (내 환경)  ──▶  eks-precheck run env.yaml  ──▶  reports/20261113-1.31-to-1.33.md
```

---

## 빠른 시작 (처음 한 번, 5분)

### 1. 준비물
- Python 3.10 이상 (`python3 --version` 으로 확인)
- (권장) GitHub CLI `gh` 로그인 상태 — GitHub API 호출 제한을 피하기 위해 사용합니다

### 2. 설치

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

설치 확인: `eks-precheck --help` 가 사용법을 보여주면 성공입니다.

> 다음에 새 터미널에서 쓸 때는 `cd eks-upgrade && source .venv/bin/activate` 만 하면 됩니다.

### 3. GitHub 토큰 설정 (권장)

```bash
export GITHUB_TOKEN=$(gh auth token)
```

`gh` 가 없으면 생략해도 실행은 되지만, 시간당 60회 제한에 걸려 add-on 분석이 일부 빠질 수 있습니다.
(GitHub → Settings → Developer settings 에서 권한 없는 토큰을 만들어 `export GITHUB_TOKEN=...` 해도 됩니다.)

---

## 사용법 (매번)

### 1단계: 입력 파일 만들기

```bash
eks-precheck init
```

현재 폴더에 `env.yaml` 이 생깁니다.

### 2단계: 내 환경 입력

`env.yaml` 을 열어 **현재/목표 버전과 사용 중인 add-on 버전**을 적습니다. 적은 것만 분석합니다.

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
- 기본 지원 add-on: `vpc-cni`, `coredns`, `kube-proxy`, `ebs-csi`, `aws-load-balancer-controller`, `karpenter`
- 내 버전을 모를 때 확인하는 명령:

  ```bash
  aws eks describe-addon --cluster-name <클러스터> --addon-name vpc-cni --query addon.addonVersion --output text
  ```

  ```bash
  kubectl get deploy -A -o jsonpath='{range .items[*]}{.spec.template.spec.containers[*].image}{"\n"}{end}' | grep -E 'karpenter|load-balancer'
  ```

<details>
<summary>목표 add-on 버전 지정 / 목록에 없는 컴포넌트 추가</summary>

```yaml
addons:
  aws-load-balancer-controller:
    current: "v2.8.1"
    target: "v2.11.0"     # 생략하면 최신 릴리스까지 분석
  cert-manager:           # 기본 목록에 없으면 repo 를 함께 적기
    current: "v1.14.4"
    repo: cert-manager/cert-manager
```
</details>

### 3단계: 실행

```bash
eks-precheck run env.yaml
```

`reports/<날짜>-<현재>-to-<목표>.md` 가 생성됩니다. VS Code 등에서 Markdown 미리보기로 열면 가장 보기 좋습니다.
화면으로 바로 보려면 `-o -`, 빨리 돌리려면 이슈 검색을 빼는 `--no-issues` 를 붙이세요.

환경이 여러 개면 파일을 나눠 두면 됩니다. 예: `eks-precheck run stg.yaml`, `eks-precheck run prd.yaml`

---

## 리포트에 담기는 내용

| 섹션 | 내용 |
|---|---|
| 요약 · 컴포넌트별 영향도 | 🔴 필수 조치 / 🟡 검토 / 🔒 보안 / 🐛 이슈 건수, add-on 별 `현재 → 목표` |
| 노드그룹 점검 | AL2 AMI 지원 종료(1.33+), kubelet 버전 차이(skew) |
| Kubernetes / EKS 변경사항 | 경로상 각 버전(예: 1.32, 1.33)의 제거 API, EKS 중요 공지, Urgent Upgrade Notes, Deprecation |
| Add-on | 현재~목표 사이 릴리스의 Breaking / 보안 / Deprecation 항목, 관련 오픈 이슈, 호환 버전 확인 명령 |
| 체크리스트 | 업그레이드 전 확인 항목, 롤백 시 주의점 |

데이터 출처: [Kubernetes Deprecation Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/),
[EKS User Guide](https://github.com/awsdocs/amazon-eks-user-guide), `kubernetes/kubernetes` CHANGELOG, 각 add-on GitHub Release/Issue.
버전별 내용은 실행할 때마다 원문에서 가져오므로 새 버전이 나와도 도구를 고칠 필요가 없습니다.

## 한계
- 분류는 키워드 기반이라 오분류·누락이 있을 수 있습니다. 최종 판단은 리포트의 원문 링크로 하세요.
- 입력한 값만 분석합니다. 매니페스트 안의 deprecated API 사용 여부는 `pluto` / `kubent` 또는 EKS 콘솔의 Upgrade Insights 로 확인하세요.
- EKS 문서는 지원 중인 버전만 포함하므로 오래된 버전 구간은 경고로 표시됩니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `eks-precheck: command not found` | `source .venv/bin/activate` 를 했는지 확인 |
| `버전 ... 을 따옴표로 감싸 주세요` | `env.yaml` 의 버전을 `"1.30"` 처럼 따옴표로 |
| `rate limit 초과` | `export GITHUB_TOKEN=$(gh auth token)` 후 재실행 (결과는 6시간 캐시됨) |
| `알 수 없는 컴포넌트` | 해당 add-on 아래에 `repo: owner/name` 추가 |

---

## (고급) 클러스터 직접 조회

입력 파일 대신 실제 클러스터를 read-only 로 조회해 버전, add-on 호환성, Upgrade Insights 를 자동으로 채울 수도 있습니다.

```bash
pip install -e '.[cluster]'
```

```bash
eks-precheck cluster --cluster my-cluster --region ap-northeast-2 --profile readonly --to 1.33
```

필요 IAM 권한 (읽기 전용): `eks:DescribeCluster`, `eks:ListAddons`, `eks:DescribeAddon`, `eks:DescribeAddonVersions`,
`eks:ListNodegroups`, `eks:DescribeNodegroup`, `eks:ListInsights`, `eks:DescribeInsight`.
쓰기 API 는 호출하지 않습니다.

## 개발

```bash
pip install -e '.[dev,cluster]'
```

```bash
pytest
```
