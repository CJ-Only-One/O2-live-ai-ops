# 03-data

라이브커머스의 데이터 계층. RDS MySQL, ElastiCache Valkey, 주문 확정 SQS,
Chat Signal SQS와 Incident Candidate 상태 DynamoDB.

`01-network` 의 출력을 remote state 로 참조한다. **apply 는 `01` 다음이다.**

## 선행 조건

`01-network/terraform.tfvars` 의 `enable_data_tier = true` 여야 한다.
그래야 private-data 서브넷과 DB/Cache 서브넷 그룹이 생긴다.

빠뜨리면 apply 초반에 멈추고 무엇을 해야 하는지 알려준다 (`data.tf` 의 precondition).
서브넷은 과금 대상이 아니므로 켜 두는 데 비용이 들지 않는다.

## backend key 가 `datastore/` 인 이유

`data/terraform.tfstate` 는 **다른 스택의 것**이다. 같은 키를 쓰면 Terraform 이
그쪽 리소스 30개를 자기 것으로 인식하고, 다음 destroy 에 전부 지운다.
근거는 [D-015](../../docs/decisions.md).

원래 백데이터 파트 소관이었으나 지금은 `06-datastream` 이 그 코드를 흡수해
같은 저장소에서 관리한다 (D-029). **키 규칙은 그대로다** — `03-data` 는
`datastore/`, `06-datastream` 은 `data/`.

## 지금 정한 것과 나중에 정할 것

인프라 구성요소는 **변경 비용**을 기준으로 나눈다.

| 지금 정한 것 | 왜 |
|---|---|
| 스토리지 암호화 | **생성 시점에만 설정 가능.** 나중에 켜려면 인스턴스 재생성 |
| 문자셋·콜레이션 | 나중에 바꾸면 기존 테이블은 그대로 남아 JOIN 이 깨진다 |
| `maxmemory-policy` | 아래 참조 |
| 마스터 비밀번호 관리 방식 | 아래 참조 |

| 나중에 정할 것 | 언제 |
|---|---|
| 인스턴스 클래스, 노드 수 | Phase 6 (부하 테스트 후) |
| Multi-AZ | 무중단 전환 가능 |
| 리드 리플리카 | Phase 6 |
| Valkey Serverless vs 노드 | Phase 6 (실측 ECPU 후) |

## 두 가지 함정

### `maxmemory-policy` 를 기본값으로 두면 재고가 사라진다

Valkey 는 재고의 **캐시가 아니라 원본**이다. `stock:{sku}` 에는 TTL 을 걸지 않는다 —
만료되는 순간 재고가 소실되기 때문이다.

그런데 축출 정책이 `allkeys-lru` 면 메모리가 찰 때 **TTL 이 없는 키도 축출 대상이
된다.** 방송 중에 재고 키가 조용히 사라지고, 다음 주문에서 Lua 스크립트가
`-2`(미초기화)를 반환한다. 로그에는 "재고 없음"만 남아 원인을 찾기 어렵다.

`volatile-lru` 는 TTL 이 있는 키만 축출한다. 세션과 상품 상세는 지워져도 다시 채우면
되고, 재고는 그렇지 않다. 그 구분이 이 파라미터 하나로 표현된다.

### 비밀번호를 Terraform 이 만들면 state 에 평문으로 남는다

`random_password` 로 만들어 넘기는 것이 흔한 패턴이지만, 그 값은 state 파일에
그대로 들어간다. `.gitignore` 의 경고와 D-005 가 말하는 것이 이것이다.

`manage_master_user_password = true` 를 쓰면 AWS 가 비밀번호를 만들어
Secrets Manager 에 넣고 로테이션까지 맡는다. **state 에는 시크릿 ARN 만 남는다.**

파드 주입은 04-platform 의 ESO 경로를 그대로 쓴다 — Datadog 키가 이미
같은 방식으로 들어가고 있다.

## TLS

Valkey 의 transit 암호화가 켜져 있다. **클라이언트가 평문으로 붙으면 연결이 끊긴다.**

```python
# redis-py
Redis(host=..., port=6379, ssl=True)
```
```javascript
// ioredis
new Redis({ host: ..., port: 6379, tls: {} })
```

AUTH 토큰은 두지 않는다. 접근 통제는 보안 그룹이 EKS 노드로 좁히고 있고,
토큰을 두면 관리 대상이 하나 늘기 때문이다. 멀티테넌시가 생기면 그때
Valkey RBAC 으로 간다.

## 큐 IAM 경계

이 스택은 큐와 ARN 출력만 소유하고 실행 역할은 소유하지 않는다.

- `04-platform`: `api`, `order-worker`, `chat-gateway`의 서비스별 Pod Identity 역할
- `08-chat-signal`: Chat Signal Lambda의 큐 소비·Candidate 테이블 쓰기 역할

역할을 데이터 스택에 합치지 않아 파드·Lambda의 배포 수명주기와 저장소 수명주기를
분리한다(D-048).

## 채팅 기반 Incident Candidate

`chat_signal.tf`는 D-047의 데이터 리소스만 소유한다.

| 리소스 | 역할 | 원문 |
|---|---|---|
| Chat Signal SQS | Chat Gateway와 Lambda 사이의 60초 분석 버퍼 | 암호화 상태로 최대 60초 |
| Incident State DynamoDB | 멱등·시간창·고유 사용자·쿨다운·Candidate | 저장 금지 |

원문 DLQ는 만들지 않는다. 처리 규칙은
[`docs/chat-incident-candidate.md`](../../docs/chat-incident-candidate.md), 입력·출력
스키마는 [`docs/contracts.md`](../../docs/contracts.md) 5.6·5.7이 원본이다. 실행
리소스는 [`08-chat-signal`](../08-chat-signal/README.md)이 소유한다.

## 명령

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

개발 기간 비용 통제는 루트 README 와 설계 문서 부록 A.3 참조.
이 스택은 독립적으로 destroy/apply 가 가능해야 한다 — 그것이 스택을 나눈 이유다.
