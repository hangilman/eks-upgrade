# eks-precheck

EKS 업그레이드 전에 **Kubernetes / EKS / Add-on 변경사항과 알려진 이슈를 한 번에 모아** 한국어 Markdown 리포트로 만들어 주는 로컬 CLI 입니다.
매번 GitHub Release 와 CHANGELOG 를 하나씩 열어 보던 사전 조사 시간을 줄이는 것이 목적입니다.

## 무엇을 모으나

| 출처 | 내용 | 리포트 분류 |
|---|---|---|
| [Kubernetes Deprecation Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/) | 해당 버전에서 제거되는 API | 🔴 |
| [EKS User Guide](https://github.com/awsdocs/amazon-eks-user-guide) (standard / extended) | 버전별 IMPORTANT 공지, 변경사항 | 🔴 / 🟡 / ℹ️ |
| `kubernetes/kubernetes` CHANGELOG | `vX.Y.0` 의 Urgent Upgrade Notes, Deprecation, API Change(제거·Action required 관련만) | 🔴 / 🟡 |
| 각 컴포넌트 GitHub Release | 현재 버전 초과 ~ 목표 버전 이하 릴리스의 Breaking / 보안 / Deprecation 항목 | 🔴 / 🔒 / 🟡 |
| GitHub Issues | 목표 버전이 언급된 open 이슈 | 🐛 |
| (선택) EKS API, kubectl | Upgrade Insights, Add-on 호환성, 노드그룹 버전·AMI 타입, self-managed 컴포넌트 이미지 태그 | 🔴 / 🟡 |

업그레이드 경로는 자동으로 계산됩니다. 예를 들어 `1.29 → 1.31` 이면 1.30, 1.31 두 단계의 변경사항을 모두 포함합니다.

## 설치

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .              # 오프라인 분석만
pip install -e '.[cluster]'   # --cluster 조회까지 (boto3)
```

GitHub API 제한(인증 없이 시간당 60회)을 피하려면 토큰을 설정하세요. 공개 레포만 읽으므로 권한 없는 토큰이면 충분합니다.
`GITHUB_TOKEN` 이 없으면 `gh auth token` 결과를 자동으로 사용합니다.

```bash
export GITHUB_TOKEN=$(gh auth token)
```

## 사용법

```bash
# 1) 오프라인: 버전만 지정 (현재 add-on 버전을 모르면 최근 5개 릴리스를 분석)
eks-precheck --from 1.29 --to 1.31

# 2) 현재 add-on 버전을 지정하면 그 사이 릴리스만 정확히 분석
eks-precheck --from 1.30 --to 1.31 --current vpc-cni=v1.18.3 --current karpenter=v1.0.6

# 3) 클러스터 read-only 조회: 현재 버전/Add-on/노드그룹/Upgrade Insights 자동 반영
eks-precheck --cluster my-cluster --region ap-northeast-2 --profile prd-readonly --to 1.31

# 일부 컴포넌트만, stdout 으로
eks-precheck --from 1.31 --to 1.32 --components vpc-cni,coredns -o -
```

리포트는 기본적으로 `reports/<날짜>-<from>-to-<to>[-<cluster>].md` 에 저장됩니다(`.gitignore` 처리됨).
작업계획서 근거로 남기려면 `git add -f reports/<file>.md` 로 커밋하세요.

주요 옵션은 `eks-precheck --help` 로 확인할 수 있습니다.

| 옵션 | 설명 |
|---|---|
| `--current NAME=VER` / `--target NAME=VER` | 컴포넌트 현재/목표 버전 지정 (반복 가능) |
| `--components a,b` | 분석할 컴포넌트 제한 |
| `--config FILE` | 컴포넌트 정의 파일 교체 |
| `--no-issues` | 이슈 검색 생략 (GitHub search API 는 분당 30회 제한) |
| `--no-cache` | 캐시(`~/.cache/eks-precheck`, 6시간) 무시 |
| `--max-items N` | 섹션당 표시 항목 수 (기본 20) |

### 목표 버전 결정 규칙

1. `--target` 으로 지정한 값
2. `--cluster` 모드이고 EKS managed add-on 이면 → 목표 Kubernetes 버전의 **기본(default) add-on 버전**
3. 그 외 → GitHub 최신 정식 릴리스

## `--cluster` 모드 필요 권한 (read-only)

```json
{
  "Effect": "Allow",
  "Action": [
    "eks:DescribeCluster", "eks:ListAddons", "eks:DescribeAddon", "eks:DescribeAddonVersions",
    "eks:ListNodegroups", "eks:DescribeNodegroup", "eks:ListInsights", "eks:DescribeInsight"
  ],
  "Resource": "*"
}
```

self-managed 컴포넌트(ALB Controller, Karpenter 등) 버전 탐지에는 `kubectl get deployments,daemonsets -A` 권한이 필요합니다(`--kube-context` 로 context 지정).
쓰기 API 는 전혀 호출하지 않으므로 운영 클러스터에서도 클러스터 상태에 영향이 없습니다.

## 컴포넌트 추가

`src/eks_precheck/data/components.yaml` 에 항목을 추가하거나, 같은 형식의 파일을 `--config` 로 넘깁니다.

```yaml
components:
  cert-manager:
    repo: cert-manager/cert-manager
    image_match: "cert-manager-controller:"
    bug_label: kind/bug
```

## 한계

- 분류는 키워드/제목 기반이라 오분류·누락이 있을 수 있습니다. 리포트의 원문 링크로 최종 확인하세요.
- EKS 문서는 지원 중인 버전(standard/extended)만 포함하므로, 지원 종료된 버전 구간은 경고로 표시됩니다.
- Karpenter / self-managed 노드는 노드그룹 점검에 포함되지 않습니다.
- 매니페스트·Helm chart 안의 deprecated API 탐지는 하지 않습니다. `pluto` 또는 `kubent` 를 함께 사용하세요.

## 개발

```bash
pip install -e '.[dev,cluster]'
pytest
```

네트워크 없이 `tests/fixtures/` 의 실제 원문 일부로 파서를 검증합니다.
