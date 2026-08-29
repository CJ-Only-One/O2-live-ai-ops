# O2 Live AI Ops — 작업 규약

**목적:** 목업 녹화본을 생방송처럼 재생하고, 그 위의 장애를 AI Agent가
안전하게 진단·대응하는 시스템입니다. 판단이 갈리면 “장애를 만들고 진단할 수
있는가”를 기준으로 합니다.

## 시작 규칙

1. 변경 전 `git status`와 대상 코드·계약을 확인합니다. 현재 구현, 목표 설계,
   미검증 상태를 구분합니다.
2. 아래 표에서 **작업과 직접 관련된 문서만** 읽습니다. 긴 문서는 인덱스에서
   절을 찾아 부분 읽기합니다.
3. 인프라 변경은 작은 대상 `plan`으로 destroy 수와 범위를 확인하고, 검증과
   롤백 방법을 함께 남깁니다.

| 작업 | 먼저 읽을 문서 |
|---|---|
| 결정·과거 함정 | `docs/decisions.md` — 인덱스 후 해당 절만 |
| 증상·오류 | `docs/troubleshooting.md` — 인덱스 후 해당 절만 |
| 실측값·용량 | `docs/measurements.md` — 인덱스 후 해당 절만 |
| API·이벤트·캐시 계약 | `docs/contracts.md` |
| Chat Candidate | `docs/chat-incident-candidate.md` |
| Candidate 이후 Agent 호출 | `docs/agent-entrypoint.md`, `contracts.md` 5.8-5.9, `docs/contracts/agent-*.schema.json` |
| 시나리오 실험·Runbook | `docs/scenario-experiment.md`, `docs/scenario-readiness.md`, `docs/runbook-catalog.md` |
| Dify 워크플로 그래프 | `docs/agent.md`, `infra/06-agent/dify/` |
| 큐시트·사전 확장 | `docs/contracts.md` 2.7, `docs/contracts/cue-sheet-v1.schema.json`, `apps/cue-warmer/` |
| 배포·특정 스택 | `README.md`, `infra/<stack>/README.md` |

`D-007`은 `decisions.md`, `D-07`은 `architecture.md`의 설계 선택입니다. 번호 자릿수를
섞어 찾지 않습니다.

## 항상 지킬 경계

| 규칙 | 실패 영향 |
|---|---|
| `03-data` state는 `datastore/`, `06-datastream` state는 `data/` | 다음 destroy에서 상대 리소스를 삭제할 수 있음 |
| ConfigMap 키 = `Settings` 필드 = `.env.example` | 값이 무시되어 `localhost` 기본값 사용 |
| Manifest `serviceAccountName` = `04-platform.app_service_accounts` | AWS 호출 시점에만 실패 |
| Terraform apply: `01` → `02` → (`03` \|\| `05` \|\| `06-datastream` \|\| `07`) → `09` → (`04` \|\| `06-agent` \|\| `08`), 로컬에서 실행 | CI는 `fmt`·`validate`만 수행 |

- WebSocket 프레임 배열, 캐시 키, 이벤트 스키마, 오류 `code`는 계약 우선입니다.
  합의 없는 변경은 금지합니다. 계약과 코드가 다르면 코드를 고칩니다.
- 무상태, 채팅 이벤트의 인입 지점 발행, graceful shutdown·지터 재연결, resource
  requests, readiness·liveness 분리, 주문 멱등성은 유지합니다 (`architecture.md` 9.4).
- Chat 분석 이벤트는 Gateway 인입에서 전용 SQS로 분기합니다. Valkey 구독 Collector를
  운영 소스로 쓰지 않습니다.
- Agent 입력은 Adapter 이후 `agent.trigger.v1`, Invocation Queue 이후
  `agent.incident.v1`을 사용합니다. 외부 채팅 원문을 Agent 입력·임베딩에 넣지 않습니다.
- Agent/Runbook은 `case → draft → 별도 검증·운영자 승인 → active`를 지킵니다.
  단일 복구 사례나 문서화는 자동 실행 권한이 아닙니다.

## 기록과 비용

- 성능·용량 수치는 `docs/measurements.md`의 실측만 사용합니다. 없으면 “안 쟀다”고
  명시합니다.
- 원인 파악이 어려웠거나 조용히 실패한 문제는 `troubleshooting.md` 형식에 기록합니다.
- 결정은 append-only로 기록하고, 같은 사실을 두 곳에 복제하지 않고 원본에 링크합니다.
- `decisions.md`, `troubleshooting.md`, `measurements.md`에 항목을 추가하면 해당
  인덱스도 함께 갱신하고 `./scripts/check-docs-index.sh [문서] [D|T|M]`를 실행합니다.
- 개인 계정 비용: NAT > RDS > EKS control plane > ElastiCache. 부하 시험은 목표의
  1/10 규모로 시작하고, 영상을 시험 경로에서 제외합니다.

이 파일은 자동 로드됩니다. 상세 규칙은 위의 원본 문서를 필요한 작업에서만 읽으며,
여기에 복제하지 않습니다.
