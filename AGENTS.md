# 작업 전에

라이브커머스 인프라·애플리케이션·배포. **이 파일은 지도이지 설명서가 아니다.**
필요한 절만 찾아 읽는다.

> 이 파일이 작업 규약의 **원본**이다. `CLAUDE.md` 와
> `.github/copilot-instructions.md` 는 여기를 가리키기만 한다.
> 도구가 달라도 읽는 내용이 같아야 하므로, 내용을 그쪽에 복제하지 않는다.

**본질:** 실시간 방송 서비스가 아니다. 목업 녹화본을 생방송처럼 재생하고
**그 위에서 생긴 장애를 AI 에이전트가 해결하는 것**이 목적이다.
판단이 갈리면 "장애를 만들고 진단할 수 있는가"를 기준으로 본다.

## 문서를 읽는 법 (토큰 절약)

`docs/decisions.md`(~29k 토큰)와 `docs/architecture.md`(~20k 토큰)는
**절대 통째로 읽지 않는다.** 둘 다 상단에 인덱스가 있다.

```bash
grep -n '^## ' docs/decisions.md        # 인덱스에서 고르고
sed -n '553,607p' docs/decisions.md     # 그 절만 읽는다
```

| 알고 싶은 것 | 문서 |
|---|---|
| 왜 이렇게 만들었나 / 함정 | `docs/decisions.md` (인덱스 → 해당 절만) |
| **막혔다 / 이 에러 본 적 있나** | `docs/troubleshooting.md` (인덱스에서 증상으로 고른다) |
| **이 숫자 어디서 나왔나 / 실측값** | `docs/measurements.md` (직접 잰 것만. 추정치는 없다) |
| 부하 수치, 캐싱, 스케일링 | `docs/architecture.md` (인덱스 → 해당 절만) |
| API·WebSocket·캐시 키·이벤트 규격 | `docs/contracts.md` |
| 채팅 기반 Incident Candidate | `docs/chat-incident-candidate.md` (**구현 전 필독**) |
| Datadog·Chat Candidate → AI Agent 공통 진입점 | `docs/agent-entrypoint.md` (**Agent 호출 변경 전 필독**) |
| 테이블·컬럼·인덱스, MySQL/Valkey 경계 | `docs/schema.md` |
| **시나리오 실험 — 복구 판정 · 주입 설정 · 초기화** | `docs/scenario-experiment.md` (**실험 돌리기 전 필독**) |
| 저장소 사용법, 배포 흐름 | `README.md` |
| 특정 인프라 스택 | `infra/<스택>/README.md` |

**`D-` 번호가 두 벌이다. 자릿수로 구분한다.**

| 표기 | 어디 | 무엇 |
|---|---|---|
| `D-007` (세 자리) | `docs/decisions.md` | 만들면서 겪은 결정 |
| `D-07` (두 자리) | `docs/architecture.md` 1절 표 | 설계 시점의 기술 선택 |

두 자리 번호를 `decisions.md` 에서 찾으면 엉뚱한 절이 나온다.

## 저장소 셋

| 저장소 | 역할 |
|---|---|
| O2-live-ai-ops (여기) | 인프라(Terraform), 앱 코드, CI |
| O2-live-deploy | k8s 매니페스트. Argo CD가 감시. **이미지 태그는 CI가 고친다** |
| o2-sdk-for-event | 이벤트 발행 SDK. 백데이터 파트 소관 |

## 어기면 조용히 깨지는 것

아래 넷은 **틀려도 파드가 정상적으로 뜬다.** 런타임에만 실패해서 알아채기 늦다.

| 규칙 | 틀리면 |
|---|---|
| `03-data`는 **`datastore/`**, `06-datastream`은 **`data/`** | 바꿔 쓰면 상대 스택 리소스를 자기 것으로 보고 다음 destroy에 지운다 |
| ConfigMap 키 == `Settings` 필드 == `.env.example` | 새 이름을 만들면 주입값이 무시되고 `localhost` 기본값이 쓰인다 |
| 매니페스트 `serviceAccountName` == `04-platform`의 `app_service_accounts` | AWS 호출에서만 실패한다 |
| apply 순서 `01`→`02`→(`03`∥`05`∥`06`∥`07`)→(`04`∥`08`), **로컬에서 사람이** | CI는 `fmt`·`validate`만 돈다. `plan`도 `apply`도 하지 않는다 (D-023) |

## 나중에 못 얹는 것

무상태 / WebSocket 프레임은 항상 배열 / 채팅 이벤트는 인입 지점에서만 발행 /
graceful shutdown + 지터 재연결 / resource requests / readiness·liveness 분리 /
주문 멱등성. 근거는 `docs/architecture.md` 9.4.

## 계약이 구현보다 우선한다

`contracts.md`와 코드가 어긋나면 **코드를 고친다.** 계약을 바꾸려면 문서를 먼저
고치고 합의한다. 특히 넷은 합의 없이 못 바꾼다 — WebSocket 프레임 포맷,
캐시 키 이름, 이벤트 스키마, 오류 `code` 체계.

채팅 분석 경로는 `docs/chat-incident-candidate.md`와 `contracts.md` 3.8·5.6·5.7을
먼저 읽는다. **Valkey 구독 Collector를 운영 소스로 만들지 않는다.** 분석 이벤트는
Chat Gateway 인입 지점에서 전용 SQS로 직접 분기한다(D-047).

Candidate 이후 Agent 호출을 바꾸면 `docs/agent-entrypoint.md`, `contracts.md` 5.8-5.9,
`docs/contracts/agent-trigger-v1.schema.json`, `docs/contracts/agent-incident-v1.schema.json`을
먼저 읽는다. Source별 JSON은 Adapter 앞에서만 다르고 Signal Queue는 `agent.trigger.v1`,
Agent Invocation Queue는 `agent.incident.v1`이어야 한다(D-050, D-055).

## 문서를 고칠 때

- 결정이 바뀌면 `decisions.md`에 **새 항목을 추가**한다. 이전 것은 지우지 않는다
- **결정을 추가하면 상단 인덱스 표에도 한 줄 넣는다.** 빠뜨리면 CI가 막는다
  (`scripts/check-docs-index.sh`). 인덱스가 낡으면 부분 읽기 전략이 무너진다
- 같은 사실을 두 곳에 적지 않는다. 한쪽이 반드시 낡는다. 링크를 건다
- 이 파일은 **매 세션 자동으로 읽힌다.** 늘리기 전에 링크로 대신할 수 있는지 본다

```bash
./scripts/check-docs-index.sh                          # 커밋 전에 한 번
./scripts/check-docs-index.sh docs/troubleshooting.md T
./scripts/check-docs-index.sh docs/measurements.md M
```

## 숫자를 지어내지 않는다

성능·용량·소요 시간을 말할 때는 **`docs/measurements.md` 에 있는 실측값**을 쓴다.
없으면 "안 쟀다" 고 하고, 필요하면 재서 그 문서에 남긴다.
추정치를 실측처럼 적으면 다음 사람이 그 위에 설계를 얹는다.

재측정은 절을 새로 만들지 말고 **그 절의 표에 행을 추가**한다. 조건이 다르면
값도 다르므로 날짜와 조건을 같이 적는다.

## 막혔던 것은 기록한다

작업 중 문제를 겪고 원인을 찾았으면 **`docs/troubleshooting.md` 에 항목을 추가한다.**
사람이 시키지 않아도 한다. 기록 기준과 항목 형식은 그 문서 상단에 있다.

짧게: **증상에서 원인이 바로 안 보였거나, 조용히 실패했거나, 자료가 실제와 달랐으면 남긴다.**
오타나 검색 한 번으로 나온 것은 남기지 않는다.

`## T-0NN.` 으로 번호를 이어 붙이고 **상단 인덱스에도 한 줄 넣는다.** 빠뜨리면 CI가 막는다.

항목의 마지막 줄인 **"왜 늦게 찾았나"** 를 빼지 마라. 다음 사람이 아끼는 시간이 거기서 나온다.

## 자주 밟는 함정

전체는 `docs/decisions.md`의 "겪은 함정" 절. 상위 넷만:

| 증상 | 원인 |
|---|---|
| `CreateContainerConfigError` | 이미지 `USER`가 이름. 숫자 UID여야 한다 |
| Valkey 연결 즉시 끊김 | transit 암호화. `rediss://`로 붙는다 |
| `ExternalSecret`이 `SecretSyncedError` | ESO 역할에 그 시크릿 ARN 권한이 없다 |
| state lock이 안 풀림 | 터미널을 끄면 락이 영원히 남는다. `force-unlock` 전 소유자 확인 |

## 비용

개인 계정이다. `NAT > RDS > EKS 컨트롤플레인 > ElastiCache` 순으로 크다.
부하 테스트는 **목표의 1/10 축소**로만 돌리고 영상은 경로에서 뺀다
(Peak 영상 egress 시간당 36 TB).
