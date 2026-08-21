# Dify 워크플로 — 알림 분류

> 이 폴더는 **Dify 안에서 만든 워크플로의 소스**다. Terraform 이 만들지 않는다.
> 알림이 여기까지 오는 경로는 [`../lambda.tf`](../lambda.tf) 와
> [`../lambda/worker.py`](../lambda/worker.py), 호스트는 [`../README.md`](../README.md).

## 왜 이 폴더가 있나

**Dify 워크플로 데이터는 EC2 루트 볼륨의 postgres 안에만 있다.**
`../ec2.tf` 가 `delete_on_termination = true` 이고 스냅샷도 없으므로,
인스턴스가 한 번 교체되면 지금까지 만든 워크플로가 전부 사라진다
(`../README.md` 의 "함정" 표, "인스턴스 교체 = 워크플로 전멸").

DSL 내보내기가 그 유일한 백업이다. 동시에 **AI 에이전트나 새로 합류한 사람이
Dify 콘솔에 들어가지 않고도 워크플로가 무엇을 하는지 읽을 수 있게** 하는 목적도 있다.

## 파일

| 파일 | 무엇 |
|---|---|
| `alert-triage.yml` | 알림 하나를 받아 원인을 추정한다. **현재 유일한 워크플로** |

워크플로가 30초를 넘기면 빠른 층 / 깊은 층으로 쪼갠다. 그때 파일이
`alert-triage-fast.yml`, `alert-triage-deep.yml` 로 늘어난다
(근거는 저장소 밖 공유 문서 `공유_Datadog-Dify-알림-파이프라인.md`).

---

## 1. 입력 계약

이 계약은 **네 곳에 동시에 박힌다.** 하나만 고치면 나머지가 조용히 어긋난다.

| 순서 | 어디 | 무엇을 맞추나 |
|---|---|---|
| 1 | Datadog → Integrations → Webhooks → `dify` → Payload | 필드 이름과 Datadog 변수 |
| 2 | [`../lambda/worker.py`](../lambda/worker.py) 의 `payload["inputs"]` | Dify 에 넘길 6~7개 선별 |
| 3 | `alert-triage.yml` 의 start 노드 `variables` | 이름·타입·필수 여부 |
| 4 | `alert-triage.yml` 의 LLM 프롬프트 | 변수 참조 |

**바꿔야 하면 코드가 아니라 이 절을 먼저 고친다.**

### 1.1 Datadog 이 보내는 것 (14필드)

```json
{
  "schema_version": "1",

  "event_id": "$ID",
  "cycle_key": "$ALERT_CYCLE_KEY",
  "monitor_id": "$ALERT_ID",
  "occurred_at": "$DATE_POSIX",

  "alert_transition": "$ALERT_TRANSITION",
  "priority": "$ALERT_PRIORITY",
  "env": "$TAGS[env]",
  "service": "$TAGS[service]",

  "alert_title": "$EVENT_TITLE",
  "alert_body": "$TEXT_ONLY_MSG",
  "alert_query": "$ALERT_QUERY",
  "host": "$HOSTNAME",
  "tags": "$TAGS",
  "link": "$LINK"
}
```

| 묶음 | 필드 | 누가 읽나 |
|---|---|---|
| 계약 | `schema_version` | Lambda. 계약이 바뀌었을 때 DLQ 의 옛 메시지를 구분한다 |
| 식별 | `event_id` `cycle_key` `monitor_id` `occurred_at` | Lambda. 로그 추적 · 중복 판정 · DLQ 신선도 |
| 분기 | `alert_transition` `priority` `env` `service` | Lambda. Recovered 폐기 · 조기 종료 · 라우팅 |
| **내용** | `alert_title` `alert_body` `alert_query` `host` `tags` `link` | **Dify** |

Lambda 가 쓰는 필드는 Dify 에 넘기지 않는다. Dify start 노드를 작게 유지하기 위해서다.

### 1.1.1 Datadog 이 보내지 않는 입력 — `past_cases`

시작 노드 변수 중 **하나는 Datadog 이 아니라 Lambda 가 만든다.**

`worker.py` 가 Dify 를 부르기 전에 이번 알림을 벡터로 바꿔
S3 Vectors 에서 비슷한 과거 인시던트를 찾고, 그 요약을 문장으로 조립해 넘긴다
(저장소는 [`../history.tf`](../history.tf)).

```
- [2026-08-14] api (monitor 14336194)
  ws_active_connections p99 급등 → 커넥션 풀 고갈로 추정
```

**Dify 는 벡터를 모른다.** 검색이 Lambda 안에서 끝나므로 지식 검색 노드도
외부 지식 API 도 붙일 필요가 없다. 여기서는 텍스트 변수 하나일 뿐이다.

검색이 실패하면 이 값만 비고 워크플로는 정상 실행된다 — 과거 사례 때문에
알림 분석 전체를 잃지 않는다.

### 1.2 변수 선택의 근거

바꾸려 할 때 왜 이걸 골랐는지 알아야 하므로 남긴다.

| 선택 | 이유 |
|---|---|
| `$TEXT_ONLY_MSG` (`$EVENT_MSG` 아님) | `$EVENT_MSG` 에는 `%%%`, 스냅샷 이미지 링크, 모니터 상태 링크 뭉치가 통째로 들어온다. 토큰 낭비이자 노이즈다 |
| `$ALERT_QUERY` 포함 | 이게 없으면 **AI 가 임계값을 모르는 채로 원인을 추측한다.** 필드 하나로 얻는 분석 품질 개선이 가장 크다 |
| `$ALERT_CYCLE_KEY` | Triggered 부터 Recovered 까지를 하나로 묶는다. 중복 판정에 `$ID` 보다 정확하다 |
| `env` `service` 만 태그에서 뽑음 | **코드에서 분기하는 태그만 뽑는다.** `cluster` `namespace` 는 K8s 모니터에만 있고 Lambda 가 분기하지 않으므로 `tags` 안에 둔다. 뽑기 시작하면 끝이 없다 |
| `$ALERT_METRIC` 제외 | 메트릭 모니터에만 값이 있다. 현재 붙인 14336194 는 APM trace 모니터라 항상 빈다 |
| `$AGGREG_KEY` 제외 | Incident Correlation 단계에서 필요해진다. `schema_version` 이 있으므로 그때 추가하는 편이 싸다 |

### 1.3 start 노드 변수

`alert-triage.yml` 이 받는 것. `$ALERT_TRANSITION` 은 Lambda 가 소비하고 끝나므로 여기 없다.

| 변수 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `alert_title` | text-input | O | |
| `alert_body` | paragraph | O | **paragraph 여야 한다.** text-input 은 기본 48자에서 잘린다 |
| `alert_query` | paragraph | X | 쿼리가 길다 |
| `priority` | text-input | X | 우선순위 미설정 모니터는 빈 문자열이 온다 |
| `host` | text-input | X | **수동 이벤트에서는 항상 빈다** |
| `tags` | paragraph | X | 실측 44자. text-input 48자 한도에 붙어 있어 paragraph 로 둔다 |
| `link` | text-input | X | |
| `past_cases` | paragraph | X | **Datadog 이 보내지 않는다.** Lambda 가 이력에서 찾아 만든다 |

> **필수를 늘리지 마라.** 필수인데 값이 비면 API 가 400 을 낸다.
> `host` 와 `priority` 는 실제로 빈 값이 온다.
> `past_cases` 도 마찬가지다 — **첫 알림에서는 항상 빈 문자열이고**,
> 비슷한 과거 사례가 없을 때도 빈다. 필수로 걸면 그때마다 400 이다.

---

## 2. 워크플로 구조

```
시작 (변수 8개) → LLM → 출력(result)
```

| 노드 | 설정 |
|---|---|
| LLM | Bedrock `Nova Lite V1` · temperature `0.2` |
| 출력 | `result` ← LLM 의 `text` |

### 2.1 프롬프트에 반드시 있어야 하는 문장

`past_cases` 를 넣었다면 이 지시도 같이 넣는다. 게시된 프롬프트의 실제 문구다.

> 과거 사례는 **참고이지 정답이 아니다.** 지금 알림의 증상과 과거 사례의 증상이나
> 원인이 겹치면 재발로 판정하고, 그 근거를 밝혀라.
> 과거 사례가 비어 있으면 "신규"로 두고 **그 사실 자체는 언급하지 마라.**

처음에는 "증상과 실제로 일치할 때만" 이었는데 **증상이 겹치는 사례에도 "신규" 가
나와서** 완화했다. 재발 판정이 지나치게 안 나오면 여기를 먼저 본다.

마지막 줄을 빼지 마라. 이력이 비는 것이 운영에서 더 흔한 상태이고, 없으면
알림마다 "과거 유사 사례가 제공되지 않았습니다" 가 출력에 붙는다.

근거는 `docs/architecture.md` 7.4 "최대 리스크: 오판의 재학습" 이다.
지금 이력에는 **사람이 검증하지 않은 판단도 들어 있다.** 그걸 사실처럼 읽으면
같은 오판을 다음 장애에서 더 큰 확신으로 반복한다. 검증된 것만 검색하도록
필터를 거는 것은 사례가 쌓인 뒤다 (`../README.md` 의 "이력 저장소" 절).

**모델은 배선 확인용이다.** 팀 표준은 `apac.amazon.nova-lite-v1:0` 이고,
판단 품질을 볼 때만 `global.anthropic.claude-sonnet-5` 나 `claude-opus-5` 로 바꾼다.
서울 리전에서는 `apac.` / `global.` 접두사가 붙은 inference profile 로만 호출되므로
드롭다운 대신 **Add Model 로 ID 를 직접** 넣는다.

응답은 이 모양으로 돌아온다.

```json
{ "data": { "status": "succeeded", "outputs": { "result": "..." } } }
```

> **`status` 를 반드시 확인해야 한다.** Dify 는 워크플로가 실패해도 HTTP 200 을 준다.
> 상태 코드만 보는 코드는 실패를 성공으로 보고하고, 그러면 재시도도 DLQ 도 동작하지 않는다.

---

## 3. 내보내기 · 가져오기

**내보내기** — Dify 스튜디오에서 앱을 열고 우측 상단 `...` → **Export DSL**.
받은 파일을 이 폴더에 같은 이름으로 덮어쓴다.

**워크플로를 고칠 때마다 다시 내보내야 한다.** 안 하면 이 파일이 곧 거짓말이 된다.

**가져오기** — 스튜디오 → 앱 만들기 → **DSL 파일 가져오기**.
가져오면 **새 앱이 생긴다.** 기존 앱을 덮어쓰지 않으므로,
복구가 목적이면 옛 앱을 먼저 지우거나 이름으로 구분한다.

가져온 뒤 반드시 두 가지를 한다.

1. **모델 재선택** — Bedrock 플러그인 설정이 환경마다 달라 그대로 안 붙을 수 있다
2. **게시(Publish)** — API 는 게시된 버전만 실행한다. 초안은 UI 에서만 돈다

### 커밋 전에 비밀값 확인

지금은 안전하다. Bedrock 을 인스턴스 역할로 쓰므로 DSL 에 키가 없다.

**Datadog 조회(pull) 노드를 붙이는 순간 위험해진다.** HTTP Request 노드에 API 키를
직접 적으면 그대로 이 파일에 실려 저장소에 올라간다. 워크플로 **환경 변수**를
`Secret` 타입으로 만들어 쓰면 DSL 에는 이름만 남는다.

```bash
grep -inE "dd-api-key|dd-application-key|Bearer |app-[a-z0-9]{16}" infra/06-agent/dify/*.yml
```

---

## 4. 이 문서를 고쳐야 하는 시점

- Datadog webhook Payload 의 필드를 늘리거나 줄일 때 → 1.1 과 1.3 을 같이 고치고 `schema_version` 을 올린다
- Dify start 노드 변수를 바꿀 때 → 1.3, 그리고 [`../lambda/worker.py`](../lambda/worker.py) 의 `inputs`
- 워크플로를 쪼갤 때 → "파일" 표에 항목을 늘린다
- 모델을 바꿀 때 → 2절
- 이력 검색 방식을 바꿀 때 → 1.1.1, 그리고 [`../lambda/worker.py`](../lambda/worker.py) 의 `_search`

**코드가 이 문서와 다르면 문서가 아니라 코드를 의심한다.**
`alert-triage.yml` 은 Dify 에서 내보낸 산출물이라 손으로 고친 흔적이 남으면 다음 내보내기에 덮인다.
