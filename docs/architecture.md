# 라이브커머스 서비스 아키텍처 설계 결정 문서

> **이 파일은 통째로 읽지 않는다.** 1,300줄, 약 20,000토큰이다.
> 여기의 `D-01`~`D-15` 는 **두 자리**다. `decisions.md` 의 세 자리 `D-0NN` 과
> 다른 체계이므로 섞어 찾지 않는다.
> 아래에서 필요한 절을 고른 뒤 `grep -n '^## 9\.' docs/architecture.md` 로
> 위치를 찾아 그 절만 읽는다.
>
> | 알고 싶은 것 | 절 |
> |---|---|
> | 목표 부하, 프로젝트 전제 | 0 |
> | 무엇을 왜 골랐는지 한눈에 | 1 (결정 요약표) · 부록 B (확정 스택) |
> | 컴포넌트 배치, 영상 파이프라인 | 2 |
> | 캐싱 계층·TTL·무효화·실패 모드 | 3 |
> | MySQL 스키마·리플리카·커넥션·암호화 | 4 |
> | Valkey를 고른 이유 | 5 |
> | Kafka/Kinesis를 안 쓰는 이유 (**커머스 경로 한정** — 에이전트 이벤트는 `decisions.md` D-027 에서 Kinesis 로 간다) | 6 |
> | 백데이터·에이전트 트레이스 | 7 (별도 파트 소관) |
> | Datadog, MCP 레이트 리밋 | 8 |
> | 스케일링, **나중에 못 얹는 앱 규약(9.4)** | 9 |
> | Phase 순서, 결정 시점 원칙 | 10 |
> | 리스크 목록 | 11 |
> | 부하 테스트·측정 항목 | 12 |
> | 아직 안 정한 것 | 13 |
>
> 코드가 이 문서와 어긋나면 `docs/decisions.md` 의 더 최근 D-번호를 먼저 본다.
> 이 문서는 설계 시점 기준이고, 실제로 부딪힌 것은 그쪽에 쌓인다.

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1 |
| 작성일 | 2026-08-13 |
| 상태 | 설계 확정, P0 진행 중 |
| 대상 시스템 | EKS 기반 라이브커머스 (뷰티 커머스 도메인) |
| 현재 프로비저닝 상태 | VPC, EKS, CI/CD(ECR·Argo CD), Datadog 연동까지 완료. 데이터 계층 없음 |

### v1.1 변경 요약

v1.0은 부하 10,000 CCU와 "VPC·EKS만 존재"를 전제로 썼다. 둘 다 사실과 달라 갱신했다.

| 바뀐 것 | v1.0 | v1.1 |
|---|---|---|
| 동시 시청자 | 10,000 | 평시 5,000 / Peak 40,000 / Stress 50,000 |
| D-01 영상 | Amazon IVS | **폐기 — OBS + MediaMTX + CloudFront** |
| D-14 상품 정보 전달 | 미결정 | **확정 — WebSocket 푸시 단일화** |
| D-15 채팅 다중 소비 | 미결정 | **확정 — 불필요, Valkey Pub/Sub만** |
| D-09 스트리밍 브로커 | 도입 안 함 | 유지. 적용 범위를 커머스 이벤트로 명시 (6.1 주석) |
| 채팅 전송 | 규정 없음 | 200ms 배치 + 표시 상한 추가 (9.4-8) |
| 프로비저닝 상태 | VPC·EKS만 | CI/CD·Argo CD·Datadog까지 완료 |

---

## 0. 전제와 범위

### 0.1 가정

**이 서비스는 실제 실시간 방송 서비스가 아니다.** 목업 녹화본을 생방송 환경으로
재생하고, **그 위에서 발생한 문제를 AI 에이전트가 해결하는 것**이 본질이다.
영상은 배경이지 주제가 아니다. v1.0에 이 한 줄이 없어서 D-01이 IVS로 갔다.

| 항목 | 값 | 근거 |
|---|---|---|
| 동시 시청자 | 평시 5,000 / 프로모션 20,000 / Peak 40,000 / Stress 50,000 | 확정 |
| RPS | 평시 500 / 프로모션 2,000 / Peak 4,000 / Stress 5,000 | 확정 |
| E2E 부하 테스트 | 위의 1/10 축소로만 실행 | 전송량 과금. 12.1 참조 |
| 방송 시간 | 60분, 1일 1-2회 | 단속적 트래픽 패턴 |
| 특가 오픈 | 방송당 1회 | 최대 스파이크 지점 |
| 조회 주기 | **폴링 없음 — WebSocket 푸시** | D-14 확정 |
| 발화율 | 평시 3%/분, 스파이크 30%/분 | 스파이크 값은 3.2에서 새로 정의 |
| DB | MySQL 확정 | |
| 관측 | Datadog 확정 | |

> 시청자 수와 RPS는 확정값이다. 발화율과 파드당 수용량은 여전히 가정이며
> Phase 4의 베이스라인 측정 결과로 갱신한다.

### 0.2 이 문서가 다루지 않는 것

- 프론트엔드 구현
- 결제 게이트웨이 연동
- 상품 카탈로그 관리 백오피스

---

## 1. 결정 요약

| # | 영역 | 결정 | 상태 |
|---|---|---|---|
| D-01 | 영상 스트리밍 | ~~Amazon IVS~~ → **OBS + MediaMTX + CloudFront** | **v1.1 교체** |
| D-02 | 채팅 | EKS에 WebSocket 게이트웨이 직접 구현 | 확정 |
| D-03 | 캐시 엔진 | ElastiCache for Valkey | 확정 |
| D-04 | 클러스터 모드 | 비활성 (Multi-AZ + Replica) | 확정 |
| D-05 | 로컬 캐시 | 인프로세스 LRU, TTL 1초, singleflight | 확정 |
| D-06 | CDN | CloudFront + Origin Shield | 확정 |
| D-07 | 재고 판정 | Valkey 원자적 DECR, MySQL 직접 차감 금지 | 확정 |
| D-08 | 비동기 큐 | SQS Standard + 멱등 키 | 확정 |
| D-09 | 스트리밍 브로커 | **Kafka/Kinesis 도입하지 않음** | 확정 (6.1 주석 참조) |
| D-10 | RDS 암호화 | 생성 시점부터 활성화 (개발환경 포함) | 확정 |
| D-11 | 무효화 채널 | Valkey Pub/Sub + TTL 안전망 병행 | 확정 |
| D-12 | 스케일링 | 큐시트 기반 사전 확장 주력, HPA/KEDA는 보정. AI는 계획하고 결정론적 Executor가 실행(D-041) | 확정 |
| D-13 | AI 에이전트 백데이터 | S3 (JSONL/Parquet) + Athena | 확정 |
| D-14 | 상품 정보 전달 | **WebSocket 푸시 단일화, 폴링 엔드포인트 미구현** | **v1.1 확정** |
| D-15 | 채팅 이벤트 다중 소비 | **불필요 — Valkey Pub/Sub만** | **v1.1 확정** |
| D-16 | 채팅 게이트웨이 런타임 | Node.js / TypeScript | v1.1 확정 |
| D-17 | 채팅 전송 | 200ms 배치 + 창당 표시 상한 | v1.1 확정 |

---

## 2. 시스템 구성

### 2.1 컴포넌트 배치

| 컴포넌트 | 배치 | 판단 근거 |
|---|---|---|
| 영상 인코딩 | OBS (송출자 로컬) | 목업 녹화본 재생이라 실시간 인코딩 부하가 없다 |
| 영상 리패키징 | EKS (MediaMTX, 파드 1개) | RTMP 수신 → HLS 변환. 트랜스코딩은 하지 않음 |
| 영상 배포 | CloudFront + Origin Shield | 세그먼트는 파일이라 엣지가 팬아웃을 흡수 |
| 채팅 게이트웨이 | EKS | 스케일링 설계 시연 대상 확보 |
| 상품·주문 API | EKS | |
| 재고 카운터 | ElastiCache Valkey | 원자적 연산 필요 |
| 주문 확정 워커 | EKS + KEDA (SQS 트리거) | |
| 정적 자산·썸네일 | S3 + CloudFront | 영상과 같은 배포판을 쓴다 |
| 방송 다시보기 | S3 (원본 녹화본) | |
| 주문·상품 원본 | RDS MySQL | |

### 2.2 영상을 IVS로 오프로드하지 않는 이유 (D-01, v1.1에서 뒤집힘)

**v1.0의 판단:** IVS는 Twitch를 구동하는 기술 기반으로, 저지연 스트리밍에서 인코더-시청자 간 3초 미만, Real-Time Streaming 모드에서 300ms 미만(최대 10,000 시청자)을 제공한다. 라이브커머스는 지연이 구매 전환에 직결되므로 자체 구현의 이득이 없다.

**뒤집힌 이유는 0.1의 전제가 빠져 있었기 때문이다.** 이 프로젝트는 실제 실시간 방송이 아니라 목업 녹화본 재생이고, 본질은 AI 에이전트의 장애 해결이다. 그 전제에서 IVS는 둘 다 어긋난다.

| 문제 | 내용 |
|---|---|
| 비용 | 시청자-시간 과금. Peak 40,000 규모의 방송 한 번이 프로젝트 예산을 넘는다 |
| 범위 | 관리형이라 **영상 파이프라인이 AI 에이전트의 진단 대상에서 빠진다.** 이 프로젝트에서는 그게 손해다 |

추가로 Real-Time Streaming 모드는 **최대 10,000 시청자**가 상한이라 Peak 40,000을 애초에 담지 못한다.

**대신 OBS가 RTMP로 송출하고 MediaMTX가 HLS로 리패키징한다.** 단 MediaMTX 단독으로는 시청자 팬아웃을 감당하지 못한다 — 40,000 × 2 Mbps는 80 Gbps이고 파드 하나가 낼 수 있는 양이 아니다. 세그먼트는 파일이므로 CloudFront가 흡수하고 **오리진은 세그먼트당 1회만 맞는다.**

| 대상 | TTL | 근거 |
|---|---|---|
| `.m3u8` 플레이리스트 | 1-2초 | 세그먼트 길이보다 짧아야 재생이 안 끊긴다 |
| `.ts` / `.m4s` 세그먼트 | 1년, immutable | 파일명이 곧 콘텐츠 식별자라 무효화가 불필요 |

지연은 HLS 2초 세그먼트 기준 glass-to-glass 6-10초다. 목업 재생이므로 IVS의 3초 미만이 필요 없다.

**채택하지 않은 더 단순한 안(기록용).** 녹화본을 `ffmpeg`로 HLS를 한 번 굽고 S3 + CloudFront에 올린 뒤, 프론트가 `방송시작시각` 기준으로 재생 위치를 계산하면 전원이 같은 지점을 본다. **스트리밍 서버가 0대다.** MediaMTX를 고른 이유는 OBS 송출 경로 자체에 시연 가치가 있고, 영상 파이프라인 장애(세그먼트 지연, 파드 축출, 인그레스트 끊김)가 Phase 7의 진단 대상을 하나 늘려주기 때문이다. 그 둘이 필요 없어지면 이쪽이 정답이다.

**대가는 명확히 적어둔다.** MediaMTX는 파드 1개 고정이고 HA가 없다. 죽으면 재시작까지 방송이 멈춘다. 목업 재생이라 감수하며, 실제 방송이 요구되면 이중화가 아니라 관리형으로 되돌아가는 것이 맞다.

### 2.3 채팅을 직접 구현하는 이유

IVS Chat이라는 관리형 대안이 존재하며, 운영 현실성만 보면 그쪽이 우세하다. 그럼에도 직접 구현하는 이유는 포트폴리오 목적상 **팬아웃, 커넥션 드레이닝, 스케일다운 시 재연결 폭풍** 같은 문제가 전부 이 컴포넌트에서 발생하기 때문이다. 스케일링 설계 역량을 보여줄 대상이 필요하다.

---

## 3. 캐싱 전략

### 3.1 라이브커머스 캐싱의 특수성

일반 커머스와 결정적으로 다른 점은 **키 공간이 극도로 좁고 트래픽이 단일 키에 집중**된다는 것이다.

| 특성 | 일반 커머스 | 라이브커머스 |
|---|---|---|
| 키 분포 | 롱테일 | 단일 키 집중 |
| 트래픽 곡선 | 완만한 일간 주기 | 방송 시각 계단식 수직 상승 |
| 커넥션 | 단발성 HTTP | 60분 지속 WebSocket |
| 스파이크 예측 | 어려움 | **정확히 알고 있음** |

방송 중 조회 대상은 실질적으로 방송 메타데이터 1건, 편성 상품 1-5건, 재고 카운터 1-5건이다. 이 조건에서는 히트율 99.9%여도 단일 키 QPS 집중이 남는다. **캐싱의 목표는 적중률이 아니라 팬아웃 흡수다.**

### 3.2 정량 근거

**채팅 팬아웃 — 먼저 용어를 정의한다**

팬아웃은 메시지 1건을 접속자 전원에게 복사해 보내는 것이다. 한 사람이 "안녕"을 치면 서버는 소켓에 40,000번 쓴다. **시청자 1명이 받는 양은 여전히 20 msg/s이고, 800,000은 서버 측 write 횟수다.**

```
[Peak 40,000]
인입:   40,000명 × 3%/분 발화       =  1,200 msg/min =     20 msg/s
아웃:   20 msg/s × 40,000 커넥션    =            800,000 전달/s
대역폭: 800,000 × 200 bytes         =  160 MB/s ≈ 1.28 Gbps
```

병목은 수신이 아니라 브로드캐스트 팬아웃이며 CPU 바운드다.

**결정적인 것은 이것이 곱셈이라는 점이다.** 동접이 고정이어도 발화율이 튀면 팬아웃은 같은 배율로 튄다. 특가 오픈 순간 발화율이 3%/분에서 30%/분이 되면:

```
인입 200 msg/s × 40,000 커넥션 = 8,000,000 전달/s
```

v1.0의 3%는 평시 값이고 스파이크 값이 아니었다. 이 구간을 견디려면 두 가지가 필요하며, 둘 다 9.4에 규약으로 넣는다.

| 대응 | 효과 | 성격 |
|---|---|---|
| 200ms 틱 배치 전송 | 프레임 수 1/4 (창당 평균 4건), 바이트는 동일 | 상시 |
| 창당 최대 N건 표시 상한 | 초과분 폐기 | **스파이크 방어 전용** |

표시 상한은 평시에 아무것도 버리지 않는다(창당 4건이라 상한에 안 닿는다). 초당 20건도 사람이 못 읽으므로 스파이크에서 버려도 사용자가 잃는 것이 없다. N은 Phase 4 측정으로 정한다.

**조회 트래픽 — D-14 확정으로 소멸**

폴링은 클라이언트가 주기적으로 "바뀐 것 있냐"고 묻는 방식이다. 3초 주기면 대부분의 답이 "없음"인데도 다음이 나간다.

```
[폴링을 유지했을 경우]
  클라이언트 → 서버   40,000 / 3s = 13,333 RPS
  서버 → Valkey       13,333 QPS  (전부 동일 키 = 핫키)

  + 로컬 캐시 1초 TTL, Pod N개 → 서버 → Valkey  N QPS
  + CloudFront 3초 TTL, Origin Shield → 오리진 ≈ 0.33 RPS

[D-14 푸시 확정 — v1.1]
  13,333 RPS 가 통째로 0 이 된다.
  재고·상품 변경이 분당 몇 건이므로 푸시는 초당 몇 건으로 끝난다.
```

v1.0의 결론은 "ElastiCache 등급을 올리는 것보다 로컬 캐시 1초가 3자릿수 배 효과적"이었다. **v1.1에서는 그보다 상위 결론이 있다 — 묻지 않는 것이 가장 싸다.** 로컬 캐시와 CloudFront의 API 캐싱 계층은 이 결정으로 존재 이유가 사라졌다(3.4에서 제외). 무효화가 푸시로 즉시 도착하므로 로컬 TTL은 안전망 역할만 남는다.

**특가 오픈 스파이크**

```
40,000명 × 30% 즉시 클릭 / 5초 창    = 2,400 RPS
MySQL 단일 row UPDATE 직렬화, 락 대기 10ms 가정 → 이론 상한 100 TPS
→ 24배 부족
```

v1.0에서 6배 부족이던 것이 24배가 됐다. Valkey `DECR`은 이 정도를 여유롭게 받으므로 **결론은 바뀌지 않고 근거만 강해진다.** 이것이 D-07(Valkey 재고 판정)의 근거다.

**영상 대역폭 — 부하 테스트를 축소해야 하는 이유**

```
Peak 영상:  40,000 × 2 Mbps × 3,600s ≈ 36 TB/시간  (CloudFront egress)
Peak 채팅:  160 MB/s × 3,600s        ≈ 576 GB/시간
```

실측 요금은 도입 직전 재확인이 필요하나, 자릿수만으로 개인 계정이 감당할 수 없다. 12.1의 부하 테스트를 1/10 축소로 고정하고 **영상은 부하 경로에서 아예 뺀다.** 부하를 받는 쪽이 CloudFront라 우리 코드의 병목을 아무것도 드러내지 않기 때문이다.

### 3.3 계층 구조

```
[Client]
   │  ① WebSocket 푸시 (D-14 확정) — 조회 폴링 없음
   ▼
[CloudFront + Origin Shield]
   │  ② 정적 자산 1년 / HLS 세그먼트 1년 / 플레이리스트 1-2초
   │     ※ API 캐싱 계층은 D-14 확정으로 없앴다
   ▼
[EKS Pod — 인프로세스 로컬 캐시]
   │  ③ TTL 1초 + singleflight          ← 효과 최대
   ▼
[ElastiCache Valkey]
   │  ④ 세션, 재고 카운터, 룸 매핑
   ▼
[RDS MySQL (+ Read Replica)]
   │  ⑤ InnoDB 버퍼 풀 (사실상 마지막 캐시 계층)
```

### 3.4 계층별 대상과 TTL

| 데이터 | 계층 | TTL | 비고 |
|---|---|---|---|
| 상품 이미지, JS/CSS | CloudFront | 1년 | 콘텐츠 해시 파일명 + immutable |
| HLS 세그먼트 | CloudFront | 1년 | 파일명이 콘텐츠 식별자 (v1.1) |
| HLS 플레이리스트 | CloudFront | 1-2s | 세그먼트 길이보다 짧아야 한다 (v1.1) |
| 방송 메타데이터 | 로컬 | 1s | **CloudFront 계층 제거** — 푸시로 전달 (v1.1) |
| 상품 상세 | 로컬 + Valkey | 1s / 60s | 무효화는 푸시로 즉시. TTL은 안전망 |
| 재고 수량 | **Valkey (원본)** | 없음 | 캐시 아님 |
| 시청자 수, 좋아요 | 로컬 | 2s | 정확도 불필요 |
| 세션, 장바구니 | Valkey | 30분 | |
| 주문 상태 | **캐싱 금지** | - | |
| 개인화 가격, 쿠폰 적용가 | **캐싱 금지** | - | 사용자별 키는 캐시 효율 0 |

### 3.5 읽기 경로

```
요청 도착
  ↓
CloudFront (Origin Shield, TTL 3s) ──히트──→ 즉시 반환
  ↓ 미스
Pod 로컬 캐시 (TTL 1s + singleflight) ──히트──→ 즉시 반환
  ↓ 미스
Valkey GET (TTL 30-60s) ──히트──→ 즉시 반환 + 로컬 채움
  ↓ 미스
MySQL read replica → Valkey 채움 → 로컬 채움 → 반환
```

`singleflight`가 로컬 캐시 미스 지점에 위치하는 것이 핵심이다. 없으면 방송 시작 순간 Pod 하나에서만 초당 수백 건의 중복 조회가 하위로 누출된다.

```javascript
const inflight = new Map();

async function getWithSingleflight(key, loader) {
  const hit = local.get(key);
  if (hit !== undefined) return hit;

  if (inflight.has(key)) return inflight.get(key);   // 진행 중 조회에 편승

  const p = loader(key)
    .then(v => { local.set(key, v, 1000); return v; })
    .finally(() => inflight.delete(key));

  inflight.set(key, p);
  return p;
}
```

### 3.6 쓰기 경로 (주문·재고)

```
주문 요청 (Idempotency-Key 헤더)
  ↓
Valkey: 원자적 DECR ← 재고 판정 지점
  ├─ 실패 → 품절 응답
  └─ 성공 ─┬─→ Pub/Sub 무효화 발행
           │
           ↓
        SQS Standard
           ↓
        Worker Pod (KEDA 스케일)
           ↓
        MySQL writer (InnoDB 트랜잭션 기록)
```

**재고 차감 Lua 스크립트**

```lua
-- KEYS[1] = stock:{sku}, ARGV[1] = 수량
local cur = tonumber(redis.call('GET', KEYS[1]))
if cur == nil then return -2 end                  -- 미초기화
if cur < tonumber(ARGV[1]) then return -1 end     -- 재고 부족
return redis.call('DECRBY', KEYS[1], ARGV[1])
```

한 번의 왕복으로 판정과 차감을 원자적으로 처리한다. 다만 차감 성공 뒤 SQS 발행이
실패하면 API가 재고와 멱등 키를 보상해야 한다. 차감과 SQS 사이에서 파드가 죽는
구간은 아직 남아 있으며, 종료 reconciliation 경로를 구현하기 전까지 알려진 구멍이다.

**표시값과 판정값의 분리**

- 화면에 "1개 남음"이 몇 초 더 보일 수 있다
- 그러나 주문은 항상 `DECR` 결과를 따르므로 오버셀은 발생하지 않는다
- 이 불일치를 제거하려 하지 말고 UX 문구로 흡수한다 ("주문 처리 중 품절되었습니다")

### 3.7 무효화

```
[상품 정보 변경]  [재고 소진]  [방송 종료]
        └──────────┬──────────┘
                   ↓
           무효화 이벤트 발행
        ┌──────────┼──────────┐
        ↓          ↓          ↓
  Valkey 키 삭제  Pub/Sub 발행  CDN TTL 만료
  (DEL 또는 갱신) (Pod 로컬 삭제) (무효화 API 미사용)
```

| 트리거 | Valkey | 로컬 캐시 | CDN | 반영 지연 |
|---|---|---|---|---|
| 상품 정보 변경 | `DEL sku:{id}:detail` | Pub/Sub 즉시 삭제 | TTL 3초 대기 | 최대 3초 |
| 가격 변경 | `DEL` + 재적재 | Pub/Sub 즉시 삭제 | TTL 3초 대기 | 최대 3초 |
| 재고 소진 | `stock:{sku}` 유지, 표시용 키만 갱신 | Pub/Sub 즉시 삭제 | TTL 3초 대기 | 판정은 즉시 |
| 방송 종료 | 영속화 경로 구현 전에는 유지 | Pub/Sub 삭제(예정) | TTL 만료 | 배치 예정 |

**CDN Invalidation API를 쓰지 않는 이유**

반영까지 수 분이 걸리고 요청 건수 과금이 발생한다. TTL 3초 리소스에 무효화를 호출하면 완료 전에 이미 만료된다. **짧은 TTL 자체가 무효화 메커니즘이다.** 정적 자산은 콘텐츠 해시 파일명(`app.a3f9c1.js`)을 쓰면 무효화가 아예 불필요하다. Invalidation은 배포 사고 등 예외 상황 전용이다.

**Pub/Sub 단독 의존 금지**

Valkey Pub/Sub은 at-most-once다. 구독자가 순간 끊겨 있으면 유실되고 재전송되지 않는다. 스케일아웃으로 새로 뜬 Pod는 이전 메시지를 받지 못한다.

따라서 **로컬 캐시 TTL이 안전망을 겸한다.** Pub/Sub 도착 시 즉시 반영, 유실 시 최대 1초 후 자연 만료. TTL을 무한으로 두면 유실된 Pod가 재시작 전까지 영구히 낡은 값을 반환한다.

```javascript
sub.subscribe('cache:invalidate');
sub.on('message', (_, payload) => {
  const { keys } = JSON.parse(payload);
  keys.forEach(k => local.delete(k));
});

// 재연결 시 전체 플러시 — 끊긴 동안의 유실 보정
sub.on('ready', () => local.clear());
```

### 3.8 3대 실패 모드

#### (1) 캐시 스탬피드 — 방송 시작 순간

**D-14로 폴링을 없앴어도 이 실패 모드는 남는다.** 푸시는 "바뀔 때 알려주는" 것이지 "처음 상태를 주는" 것이 아니라서, 접속자는 여전히 진입 시 1회 초기 상태를 읽어야 한다. 방송 시작 30초에 40,000명이 몰리면 **1,333 RPS의 초기 적재가 콜드 캐시를 그대로 통과해 MySQL로 향한다.**

폴링과 다른 점은 이것이 **1회성이고 시각을 정확히 알고 있다**는 것이다. 그래서 대응 A(사전 워밍)의 효과가 v1.0보다 크다.

**대응 A — 사전 워밍.** 방송 스케줄을 알고 있다는 이점을 활용한다.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cache-warmer
spec:
  schedule: "40 19 * * *"      # 방송 20분 전
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: warmer
              image: <ECR>/cache-warmer:latest
```

**대응 B — singleflight.** (3.5 참조)

**대응 C — 확률적 조기 갱신.** TTL 만료 시점 집중을 분산한다.

```javascript
if (now - delta * beta * Math.log(Math.random()) >= expiry) {
  refreshInBackground(key);   // 기존 값은 그대로 반환
}
```

#### (2) 핫 키

단일 키에 트래픽이 집중되면 클러스터 샤딩이 무력화되고 해당 슬롯 노드만 포화된다.

1차 방어는 로컬 캐시다. 부족하면 키를 복제한다.

```javascript
const REPLICAS = 8;
const key = `sku:${id}:detail:${Math.floor(Math.random() * REPLICAS)}`;
// 쓰기 시 8개 전부 갱신, 읽기 시 랜덤 1개
```

쓰기 비용이 8배가 되지만 방송 상품은 쓰기가 극히 드물어 유리한 교환이다. 읽기 분산은 Replica 증설 + reader endpoint가 샤드 추가보다 효과적이다.

#### (3) 무효화 지연

(3.7 참조) Pub/Sub + TTL 이중화로 최대 지연을 1초로 제한한다.

### 3.9 키 스키마

전체 키와 구현 상태는 `contracts.md` 4를 원본으로 삼는다.

`stock:{sku}`에 TTL을 걸지 않는다. 만료되는 순간 재고가 소실된다. 종료 재고의
영속화 스키마와 배치는 아직 미구현이므로, 그 경로가 생기기 전에는 방송 종료만으로
키를 삭제하지 않는다.

### 3.10 흡수율 목표

| 계층 | 목표 |
|---|---|
| CloudFront | 정적 자산 95% 이상 |
| 로컬 캐시 | 방송 메타·상품 조회 90% 이상 |
| Valkey | 나머지 대부분 |
| MySQL | 전체 읽기의 1% 미만 |

---

## 4. 데이터 계층 (MySQL)

### 4.1 InnoDB 버퍼 풀

MySQL 8.0에서 쿼리 캐시는 제거되었다. 내부 캐시는 InnoDB 버퍼 풀 하나뿐이며 기본값은 인스턴스 메모리의 약 75%다.

```sql
SELECT
  (1 - (
    SELECT VARIABLE_VALUE FROM performance_schema.global_status
    WHERE VARIABLE_NAME='Innodb_buffer_pool_reads'
  ) / (
    SELECT VARIABLE_VALUE FROM performance_schema.global_status
    WHERE VARIABLE_NAME='Innodb_buffer_pool_read_requests'
  )) * 100 AS hit_rate_pct;
```

목표 99% 이상. 라이브커머스는 활성 데이터셋이 작아(상품 수십 건, 주문 수천 건) 달성이 어렵지 않다.

### 4.2 리드 리플리카 라우팅

RDS MySQL 리플리카는 비동기 복제다. 주문 직후 조회를 리플리카로 보내면 "주문 없음" 응답이 나갈 수 있다.

| 쿼리 | 라우팅 |
|---|---|
| 상품 목록, 방송 편성 | replica |
| 주문 내역 조회 (일반) | replica |
| 주문 완료 직후 상세 조회 | **writer** |
| 재고 관련 모든 읽기 | Valkey (MySQL 조회 안 함) |

`ReplicaLag` 지표에 알림 필수. 방송 중 대량 INSERT 시 지연이 튄다.

### 4.3 커넥션 수 통제

```
Pod 20개 × 커넥션 풀 20 = 400 커넥션
+ 워커 Pod 10개 × 10   = 100
+ 마이그레이션, 운영 접속  =  20
────────────────────────────────
합계 520 커넥션
```

`max_connections`는 인스턴스 메모리 기반으로 산정되며 소형 인스턴스에서는 낮다.

**대응**
1. 앱 커넥션 풀 상한을 Pod당 5-10으로 축소 — 읽기가 1 qps 미만이므로 큰 풀이 불필요하다
2. 그래도 부족하면 RDS Proxy 도입 (페일오버 시간도 단축)

캐싱이 제대로 되면 1번만으로 충분하다. **커넥션 풀 축소는 캐싱 전략의 결과물이다.**

### 4.4 스키마

```sql
CREATE TABLE orders (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  idem_key     CHAR(36)     NOT NULL,
  sku_id       BIGINT       NOT NULL,
  user_id      BIGINT       NOT NULL,
  qty          INT          NOT NULL,
  created_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_idem (idem_key),
  KEY idx_sku_created (sku_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

`uk_idem`이 워커 재처리 시 중복 주문을 막는 최종 방어선이다. SQS Standard는 최소 1회 전달이므로 중복은 정상 동작 범위다.

### 4.5 MySQL에서 재고를 직접 차감하지 않는 이유

```sql
-- 이 쿼리는 초당 100건 수준에서 막힌다
UPDATE stock SET qty = qty - 1 WHERE sku_id = 12345 AND qty > 0;
```

동일 행 X 락이 직렬화되고, 기본 격리 수준 `REPEATABLE READ`에서 갭 락까지 잡혀 데드락 확률이 상승한다. 특가 오픈 600 RPS를 감당할 수 없다.

### 4.6 암호화 (D-10)

**RDS 스토리지 암호화는 생성 시점에만 설정 가능하다.** 이후 활성화하려면 스냅샷 → 암호화 복사 → 복원, 즉 인스턴스 재생성과 커트오버가 필요하다.

추가 제약:
- 미암호화 인스턴스의 암호화 스냅샷 생성 불가
- 미암호화 백업을 암호화 인스턴스로 복원 불가
- 암호화 인스턴스의 미암호화 리드 리플리카 불가 (역도 동일)

관리형 키(`aws/rds`) 기준 추가 비용이 없고 성능 영향도 없으므로 **개발환경도 처음부터 켠다.**

```hcl
resource "aws_db_instance" "main" {
  storage_encrypted = true
  kms_key_id        = null   # null이면 aws/rds 관리형 키
}
```

**개발환경에서 실제로 미뤄도 되는 항목**

| 항목 | 개발환경 |
|---|---|
| Multi-AZ | 끄기 (나중에 무중단 전환) |
| 백업 보존 기간 | 1일 또는 0 |
| Deletion Protection | 끄기 |
| Performance Insights | 무료 티어 7일 |
| Enhanced Monitoring | 끄거나 60초 |
| 인스턴스 클래스 | `db.t4g.micro` |
| **스토리지 암호화** | **켜기** |

---

## 5. 캐시 엔진 선택 (D-03)

### 5.1 Valkey란

2024년 3월 Redis Ltd.가 라이선스를 BSD-3에서 SSPLv1/RSALv2 듀얼로 변경하자, 7일 만에 Linux Foundation이 마지막 BSD 릴리스인 Redis 7.2.4를 포크한 프로젝트다. AWS, Google Cloud, Oracle, Ericsson, Snap이 창립 기여자이며 프로젝트 리드는 전 Redis 코어 메인테이너다.

- 명령어, 자료구조, 프로토콜이 Redis와 동일 → 클라이언트 라이브러리 무변경
- RDB/AOF 포맷 호환 → ElastiCache에서 Redis OSS 7.2 → Valkey 무중단 인플레이스 업그레이드 가능
- 학습 비용 0

### 5.2 Redis가 부적합한 것은 아니다

"Redis는 더 이상 오픈소스가 아니다"는 **현재 기준 틀린 진술이다.** Redis 8.0(2025년 5월)부터 AGPLv3 / SSPLv1 / RSALv2 트라이 라이선스로 배포되며 AGPLv3는 OSI 승인 오픈소스다.

| 상황 | AGPL 의무 |
|---|---|
| Redis를 캐시로 사용 | **없음** |
| 컨테이너로 배포해 자사 서비스에 사용 | **없음** |
| 소스 수정 후 네트워크 서비스로 제공 | 소스 공개 의무 |
| 관리형 Redis 판매 | SSPL/RSAL 대상, 상용 계약 필요 |

본 프로젝트는 첫 번째 줄이며 아무 의무도 발생하지 않는다.

### 5.3 그럼에도 Valkey를 선택한 근거

1. **가격** — ElastiCache에서 노드 기준 20%, Serverless 기준 33% 저렴
2. **버전** — ElastiCache의 Redis OSS 엔진은 라이선스 변경 이전 계열에 묶여 있어 Redis 8 기능(Vector Sets 등)을 쓸 수 없다. ElastiCache 안에서의 실제 선택지는 Valkey 8.x/9.x vs Redis 7.x다
3. **라이선스** — BSD-3라 법무 검토 부담이 없다 (조직에 따라 AGPL을 금지 목록에 두는 경우 존재)

**이는 엔진 품질 판단이 아니라 AWS 관리형 서비스 내에서의 가격·버전 판단이다.** EKS에 직접 배포하거나 Redis 8 모듈이 필요하면 Redis가 맞다.

### 5.4 배포 모드

| 결정 | 선택 | 근거 |
|---|---|---|
| 클러스터 모드 | **비활성** | 핫키가 단일 키이므로 샤딩 이득 없음, 운영 복잡도만 증가 |
| 복제 | Multi-AZ + Replica 2 | 읽기 분산 + 페일오버 |
| Serverless vs 노드 | 방송 패턴 단속적 → Serverless 유리 | 로컬 캐시로 QPS가 한 자릿수이므로 ECPU 소모 극소 |

가격은 리전·시점에 따라 변동하므로 도입 직전 ElastiCache 요금 페이지에서 확인한다.

### 5.5 성능 비교

Valkey 8.x는 멀티스레드 I/O 도입으로 Redis OSS 7.x 대비 처리량 약 8% 증가, p99 지연 약 22% 감소, 메모리 약 20% 감소가 보고되었다. 단 Redis 8도 대폭 개선되었으므로 최신 버전끼리는 다르다.

**본 프로젝트 규모에서는 성능이 선택 기준이 되지 않는다.** 로컬 캐시 적용 후 캐시 계층 QPS는 한 자릿수이며, 엔진 간 8% 차이는 무의미하다.

---

## 6. 메시징 (D-09)

### 6.1 결론

**Kafka와 Kinesis 모두 도입하지 않는다.** SQS Standard로 충분하다.

> **v1.1 주석 — 이 결정의 적용 범위.**
>
> D-09가 다루는 것은 **커머스 이벤트 경로**다. 주문 확정, 재고, 캐시 무효화 —
> 이 문서가 설계하는 범위 안의 이벤트들이고, 6.2·6.3의 판단은 전부 그것들에
> 대한 것이다. 여기에는 SQS Standard와 Valkey Pub/Sub만 쓴다.
>
> **AI 에이전트용 백데이터·데이터 스트림은 별도 파트가 맡는다.** 계정에
> Kinesis·Firehose·Glue가 이미 떠 있는 것은 그쪽 작업이며, 무엇을 쓸지는
> 그 파트가 정한다. **이 문서의 범위 밖이다.**
>
> 7장(AI 에이전트와 백데이터)도 같은 선으로 읽어야 한다. 7.2의 구조도는
> 이 문서가 지시하는 설계가 아니라 **연동 지점을 이해하기 위한 배경**이다.
> 커머스 쪽이 책임지는 것은 "어떤 이벤트를 어떤 스키마로 발행하는가"까지이고,
> 그 뒤의 수집·저장·분석 경로는 담당 파트의 결정이다.
>
> 커머스 쪽에서 실제로 지켜야 할 것은 하나뿐이다 —
> **`03-data`의 Terraform backend key를 `datastore/`로 둔다.**
> `data/`는 그쪽이 쓰고 있어 겹치면 서로의 리소스를 지운다.

### 6.2 정량 근거

| 이벤트 | 발생량 (Peak 40,000) | Kafka 단일 파티션 용량 |
|---|---|---|
| 채팅 메시지 인입 | 20 msg/s | 수만 msg/s |
| 주문 확정 (스파이크) | 2,400 msg/s × 30초 | 수만 msg/s |
| 캐시 무효화 | 분당 수 건 | - |
| AI 에이전트 트레이스 | 0.002 msg/s | - |

모든 항목이 단일 파티션 용량의 1% 미만이다.

### 6.3 판단 기준 체크리스트

처리량이 아니라 아래 조건이 기준이다.

| 조건 | 설명 | 현재 |
|---|---|---|
| 다중 독립 컨슈머 | 동일 이벤트를 3개 이상이 서로 다른 속도로 소비 | ✗ 주문은 단일 워커 |
| 재생(replay) | 오프셋 되감아 과거 이벤트 재처리 | ✗ (S3로 충족) |
| 파티션 순서 + 고처리량 동시 | 키 단위 순서 + 초당 수만 건 | ✗ 순서 무관, 멱등 처리 |
| 장기 이벤트 로그 | 이벤트 소싱, CDC | ✗ MySQL이 원본 |

SQS와의 본질적 차이는 처리량이 아니라 **소비 모델**이다. SQS는 소비 시 메시지가 삭제되므로 단일 컨슈머 전제다.

### 6.4 비용

| 옵션 | 최소 비용 (us-east-1 기준) |
|---|---|
| SQS | 요청당 과금, 유휴 시 0 |
| Valkey Streams | **0** (기존 ElastiCache 재사용) |
| Kinesis Data Streams | 2 샤드 기준 월 약 $21.6 + PUT |
| MSK Provisioned | 3 브로커 최소 구성 월 약 $460 |
| MSK Serverless | 클러스터 시간만 월 약 $547 |

MSK에는 프리 티어가 없다. 5 msg/s를 위해 월 $460-547 지출은 정당화 불가능하다.

### 6.5 재검토 트리거

아래 중 **2개 이상** 충족 시 재검토한다. 1개만 걸리면 Valkey Streams를 먼저 본다.

```
□ 동일 이벤트를 소비하는 독립 컨슈머가 3개 이상이 된다
□ 워커 버그로 과거 이벤트를 재처리해야 하는 상황이 실제로 발생한다
□ 이벤트 처리량이 지속적으로 초당 1만 건을 넘는다
□ MySQL CDC로 검색 인덱스나 분석 저장소를 동기화해야 한다
□ 이벤트를 7일 이상 보존해야 한다
```

### 6.6 대안 우선순위

| 대안 | 장점 | 단점 |
|---|---|---|
| **Valkey Streams** | 추가 인프라 0, 컨슈머 그룹 지원 | 보존 짧음, 메모리 제약 |
| Kinesis Data Streams | AWS 네이티브, 저렴, 재생 지원 | Kafka 생태계 도구 불가 |
| SNS → 다중 SQS | 가장 단순, 저렴 | 재생 불가 |
| MSK | Kafka 생태계 전체 | 비용, 운영 부담 |

채팅 이벤트를 여러 소비자(모더레이션, 실시간 집계, 아카이브, AIOps)가 쓰게 되면 Valkey Streams가 첫 후보다.

```
XADD chat:stream:{bcast} MAXLEN ~ 100000 * user 123 msg "..."
XREADGROUP GROUP moderation c1 COUNT 100 STREAMS chat:stream:{bcast} >
```

`MAXLEN`으로 보존량을 제한해 메모리 폭증을 막는다.

### 6.7 포트폴리오 관점

리뷰어의 첫 질문은 "왜 Kafka인가"다.

- 5 msg/s에 MSK를 붙였다면 → 과잉 설계로 감점
- "SQS로 충분해서 SQS를 썼고, Kafka는 이런 조건에서 도입한다"고 답할 수 있으면 → 가점

인프라 직군에서 반복 확인하는 것이 "근거 없는 기술 도입을 하지 않는가"다. Kafka 경험 자체가 목적이면 CDC(Debezium + MySQL binlog)나 로그 수집 파이프라인 같은 **별도 프로젝트로 분리**한다.

---

## 7. AI 에이전트와 백데이터 (D-13)

> **v1.1 범위 주석.** 이 장은 **별도 파트(AI 에이전트 백데이터·데이터 스트림)의
> 영역**이다. 아래 내용은 이 문서가 지시하는 설계가 아니라 연동 지점을 이해하기
> 위한 배경으로 읽어야 한다. 실제 수집·저장·분석 경로의 결정권은 그 파트에 있고,
> 이미 계정에 그쪽 구성이 올라가 있다.
>
> **커머스 쪽이 책임지는 경계는 "어떤 이벤트를 어떤 스키마로 발행하는가"까지다.**
> 그 계약만 Phase 1에서 맞추면 되고, 그 뒤는 관여하지 않는다.

### 7.1 요구사항 분해

"에이전트로 문제를 해결하고 처리 과정을 백데이터로 활용"은 두 가지가 섞여 있다.

| 요구 | 성격 | 필요한 것 |
|---|---|---|
| 실시간 신호 전달 | 전송 | Datadog MCP + EventBridge (설계됨) |
| 처리 과정 축적 | **저장** | append-only 영구 저장소 + 분석 쿼리 |

Kafka는 전송 계층이며 기본 보존이 일 단위다. 영구 보존은 결국 S3다. **"append-only 로그가 필요하다"가 "Kafka가 필요하다"는 아니다.**

### 7.2 구조

```
[원천 신호]
  Datadog (로그, 메트릭, 트레이스)
        │
        ▼ 알람
  EventBridge → Lambda → Bedrock Agent
        │
        ├──► Datadog Agent Observability   (실시간 관측, 단기)
        │
        └──► S3  (JSONL → Parquet)         (영구 백데이터)
                  │
                  ├─ Athena          분석 쿼리, MTTR 통계
                  ├─ Knowledge Base  유사 사례 RAG
                  └─ 평가셋          에이전트 회귀 테스트
```

Datadog은 관측과 단기 조회, S3는 영구 축적과 분석으로 역할을 나눈다. Datadog 보존 기간 연장보다 S3가 훨씬 저렴하다.

발생량은 월 약 5,000건 / 25MB(초당 0.002건) 수준으로 버퍼링도 불필요하다. Lambda에서 S3로 직접 쓴다.

### 7.3 트레이스 스키마

사후 구조화는 대부분 실패한다. 처음부터 분석 가능한 형태로 저장한다.

```json
{
  "schema_version": "1.0",
  "incident_id": "inc-2026-0813-001",
  "trace_id": "abc123",
  "started_at": "2026-08-13T19:42:11.320Z",
  "trigger": {
    "source": "datadog_monitor",
    "monitor_id": 4471,
    "severity": "warning"
  },
  "context": {
    "service": "chat-gateway",
    "cluster": "live-prod",
    "signal_summary": "ws_active_connections p99 spike"
  },
  "agent": {
    "steps": [
      {"n": 1, "tool": "search_datadog_logs", "latency_ms": 820, "tokens_in": 1200, "tokens_out": 340}
    ],
    "hypothesis": "...",
    "action_taken": "none | recommended | executed",
    "total_tokens": 4820,
    "duration_ms": 18400
  },
  "outcome": {
    "resolved": true,
    "mttd_sec": 42,
    "mttr_sec": 310,
    "root_cause_label": "connection_pool_exhaustion",
    "human_verified": true,
    "human_correction": null
  }
}
```

S3 경로 파티셔닝을 미리 정한다. Athena 스캔 비용이 갈린다.

```
s3://<bucket>/agent-traces/dt=2026-08-13/service=chat-gateway/inc-2026-0813-001.json
```

### 7.4 최대 리스크: 오판의 재학습

에이전트가 잘못 판단한 사례를 검증 없이 RAG 코퍼스에 넣으면, 다음 장애에서 같은 오판을 더 확신을 갖고 반복한다.

| 리스크 | 대응 |
|---|---|
| 오판 사례 재학습 | `human_verified=true`인 항목만 RAG 인덱싱 |
| 표본 편향 (해결된 건만 축적) | 미해결·오판 사례도 라벨 붙여 저장 |
| 로그 내 민감정보 유입 | S3 적재 전 마스킹, KMS 암호화 |
| 스키마 드리프트 | `schema_version` 필드, Glue 카탈로그 관리 |

**이 문제는 저장소 선택으로 해결되지 않는다.** 요구사항의 본질이 스트리밍이 아니라는 방증이기도 하다.

---

## 8. 관측 (Datadog)

### 8.1 도입 경로

AWS Marketplace를 통해 구독하면 AWS 청구서에 합산된다. PAYG, 계약형, Private Offer, GovCloud 리스팅이 존재하며 조직 도입 시 Private Offer가 리스트 가격보다 유리하다.

Datadog은 SaaS이므로 데이터 저장·처리는 Datadog 인프라에서 이루어진다. 데이터 반출 정책과 리전(US1/EU1/AP1) 선택을 별도 검토한다.

### 8.2 부수 비용 (Datadog 요금과 별개)

- CloudWatch `GetMetricData` API 호출
- Metric Streams + Firehose 사용 시 스트림·전송
- 로그 포워더 Lambda 실행
- NAT Gateway 경유 데이터 전송

Datadog 청구액에 상응하거나 더 큰 금액이 AWS 측에 청구되는 사례가 보고된다. 구조적 이중 비용이므로 통합 설정에서 리소스 제외 규칙을 먼저 잡는다.

Datadog 과금 대상은 EC2 호스트, Lambda 함수, CloudWatch 커스텀 메트릭이며 필터링 가능한 그 외 서비스 통합 메트릭은 과금되지 않는다. 단 Metric Streams를 Kinesis 방식으로 쓰면 Datadog 통합 페이지의 제외 규칙이 적용되지 않으므로 AWS 콘솔에서 직접 관리해야 한다.

### 8.3 Bedrock 에이전트 연동

Datadog MCP Server(2026년 3월 GA)를 AgentCore Gateway의 MCP 타깃으로 등록한다.

```
https://<DATADOG_MCP_ENDPOINT>?toolsets=core,kubernetes&omit_tools=create_datadog_notebook
```

- 인증: 헤드리스이므로 OAuth 대신 Service Access Token을 `Authorization` 베어러로 전달, Secrets Manager 보관
- 권한: `mcp_read`만 부여로 시작 (`mcp_write`는 모니터 삭제·뮤트 가능)
- Bedrock Responses API에서 Gateway ARN을 tool connector로 지정하면 서버 사이드 툴 실행이 되어 오케스트레이션 루프 구현이 불필요하다

### 8.4 레이트 리밋 (최대 병목)

MCP Server 공정 사용 한도는 10초당 50회 버스트, **월 50,000회 툴 콜**이다. 한 번의 장애 조사에 20-30회를 소모한다고 보면 월 1,500-2,500건이 상한이다. 상시 폴링 설계는 여기서 깨진다.

```
count:datadog.mcp.tool.usage{*} by {tool_name}.as_count()
```

분포 메트릭이므로 `sum`이 아닌 `count` + `.as_count()`를 쓴다. 한도의 80% 지점에 모니터를 건다.

### 8.5 프롬프트 인젝션

로그 본문에 `"Ignore previous instructions..."` 같은 문자열이 포함될 수 있다. **로그·트레이스 내용은 신뢰할 수 없는 데이터로 취급**하고, 그 내용을 근거로 툴 실행이나 인프라 변경을 자동 수행하지 않도록 시스템 프롬프트와 승인 게이트에서 차단한다.

---

## 9. 스케일링 (D-12)

### 9.1 반응형 스케일링의 한계

**Pod 스케일업**

```
메트릭 스크랩 주기            15s
HPA 컨트롤러 동기화 주기      15s
스케줄링                       1s
이미지 pull (노드 캐시됨)      2s
애플리케이션 부팅         10 - 30s
─────────────────────────────────
합계                      43 - 63s
```

**노드까지 필요한 경우 (Karpenter)**

```
NodeClaim → EC2 launch        20 - 40s
kubelet Ready                 15 - 25s
이미지 pull (콜드)            30 - 60s
+ 위 Pod 스케일업
─────────────────────────────────
합계                     110 - 190s
```

방송 시작 스파이크는 30초 내 완료된다. **반응형 스케일링만으로는 구조적으로 불가능하다.**

### 9.2 4계층 대응

| 계층 | 방식 | 도구 |
|---|---|---|
| 1차 (주력) | 큐시트 기반 사전 확장 | Capacity Planner + 결정론적 Executor (D-041) |
| 2차 (보정) | 커스텀 메트릭 반응형 | HPA/KEDA. 첫 스파이크 해결책은 아님 |
| 3차 (버퍼) | 오버프로비저닝 pause Pod | 음수 PriorityClass |
| 4차 (최후) | 노드 자동 확장 | Karpenter |

AI Agent 는 큐시트와 실측값으로 용량 계획을 제안하고 설명하지만 `scale` 을 직접
소유하지 않는다. 검증된 구조화 계획만 Executor가 멱등하게 실행한다. 큐시트가
없거나 오래됐을 때의 baseline, 노드→Pod 사전 확장 순서, 축소 게이트, Argo CD와
replica 소유권, Dify 예외는 D-041에 기록한다.

아래 KEDA cron 은 **매일 같은 시각에 반복되는 고정 방송**의 단순 예시다. 큐시트가
방송마다 달라지는 경로에서는 이 YAML 을 Agent가 계속 고치지 않고 D-041의
`CapacityPlan` 과 Executor를 쓴다.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: chat-gateway
spec:
  scaleTargetRef:
    name: chat-gateway
  minReplicaCount: 2
  maxReplicaCount: 20
  cooldownPeriod: 600        # 방송 종료 후 급격한 축소 방지
  triggers:
    - type: cron
      metadata:
        timezone: Asia/Seoul
        start: "40 19 * * *"
        end: "30 21 * * *"
        desiredReplicas: "8"
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring:9090
        query: sum(ws_active_connections)
        threshold: "5000"
```

```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: overprovisioning
value: -10
globalDefault: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: overprovisioning
spec:
  replicas: 3
  template:
    spec:
      priorityClassName: overprovisioning
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.9
          resources:
            requests:
              cpu: 500m      # 실제 워크로드 request와 동일
              memory: 1Gi
```

음수 우선순위이므로 실제 Pod 진입 시 즉시 축출되고, 노드는 이미 확보되어 있다. 노드 대기 60-120초를 0으로 만든다.

### 9.3 Karpenter 주의점

방송 중 consolidation이 동작하면 노드 통합으로 Pod가 재배치되어 WebSocket이 끊긴다.

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: chat
spec:
  disruption:
    consolidationPolicy: WhenEmpty      # WhenEmptyOrUnderutilized 아님
    consolidateAfter: 30m
  template:
    spec:
      taints:
        - key: workload
          value: chat
          effect: NoSchedule
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]         # 채팅은 Spot 금지
```

방송 시간대 Pod에 `karpenter.sh/do-not-disrupt: "true"` 어노테이션을 추가해 이중으로 막는다. 주문 확정 워커와 배치 작업은 Spot으로 비용을 상쇄한다.

### 9.4 애플리케이션 코드 규약 (나중에 못 얹는 항목)

1. **완전한 무상태** — 세션·장바구니·룸 매핑을 Pod 메모리에 두지 않는다
2. **Graceful shutdown**

```javascript
process.on('SIGTERM', async () => {
  server.close();
  await broadcastCloseFrame(1001, 'going away');
  await sleep(15000);
  process.exit(0);
});
```
```yaml
spec:
  terminationGracePeriodSeconds: 60   # 기본 30초로는 부족
```

클라이언트에 지터 지수 백오프 재연결 필수. 없으면 스케일다운이 곧 장애다.

3. **resource requests 명시** — 없으면 HPA 미동작, Karpenter 사이징 불가
4. **readiness / liveness 분리** — `readyz`에서만 의존성 체크. `healthz`에서 하면 DB 순단 시 전체 재시작 루프
5. **커스텀 메트릭 노출** — `ws_active_connections`, `ws_broadcast_queue_depth`
6. **주문 API 멱등성** — `Idempotency-Key` 헤더
7. **부팅 시간 최소화** — 부팅 30초는 스케일업 전체를 30초 지연시킨다

8. **채팅 배치 전송 + 표시 상한** (v1.1 추가, D-17)

```javascript
// 메시지당 1프레임으로 보내면 Peak에서 write가 초당 800,000회다.
// 200ms 창에 모아 배열 하나로 보낸다. 창당 최대 N건, 초과분은 버린다.
setInterval(() => {
  for (const conn of connections) {
    const batch = conn.pending.splice(0, MAX_PER_TICK);   // 초과분 폐기
    if (batch.length) conn.send(JSON.stringify({ t: 'chat', items: batch }));
    conn.pending.length = 0;
  }
}, 200);
```

**이것은 나중에 못 얹는다.** 프레임 페이로드가 배열이어야 하므로 WebSocket
메시지 계약이 처음부터 그렇게 정해져 있어야 한다. 단건 포맷으로 출발하면
클라이언트까지 전부 고쳐야 한다. `MAX_PER_TICK`은 Phase 4 측정으로 정한다.

### 9.5 ALB deregistration delay

기본 300초는 WebSocket에 과하다. 60초 수준으로 조정한다. 너무 짧으면 진행 중 주문이 끊기고, 너무 길면 배포가 느려진다.

---

## 10. 구축 순서

### 10.1 Phase

> **진행 상황 정정 (저장소 기준).** Phase 0~3 은 끝났다. `03-data` 는 apply 되어
> 있고 backend key 는 `datastore/` 다. `data/` 고아 state 는 정리 대상이 아니라
> `06-datastream` 으로 흡수됐다 (D-029). 앱 네 개도 배포되어 돌고 있다.
> **지금 위치는 Phase 4 앞이다** — 영상 스택(`07-media`, D-033)과 베이스라인
> 측정이 남았다. 아래 표의 일정은 원안 그대로 둔다.

```
Phase 0  전제 갱신 + 고아 state 정리                 (1일)    ← 완료
Phase 1  인터페이스 계약 확정                        (2-3일)
Phase 2  03-data + 07-media 프로비저닝               (2-3일)
Phase 3  애플리케이션 개발 (9.4 규약 준수)           (3-4주)
Phase 4  단일 Pod 배포 + 베이스라인 측정             (2-3일)  ← 분기점
Phase 5  KEDA + 오버프로비저닝 + ALB 튜닝            (1주)
Phase 6  축소 부하 테스트 → 사이징 확정              (1주)
Phase 7  장애 시나리오 주입 + AIOps 파이프라인       (1-2주)
```

v1.0에서 달라진 것 셋.

- **Phase 0의 내용이 바뀌었다.** 부하 프로파일은 확정됐으므로, 대신 `data/terraform.tfstate` 고아 state 정리가 들어간다. **이걸 치우기 전에는 Phase 2를 시작할 수 없다** — 새 `03-data`가 같은 키를 쓰면 남의 스택 30개를 자기 것으로 인식한다. `03-data`의 backend key는 `datastore/`로 간다.
- **Phase 2에 영상 스택이 추가됐다.** D-01 교체로 생겼다. 번호는 `05-media` 로 예약했으나 05·06 을 관측·에이전트·백데이터 스택이 먼저 가져가 `07-media` 가 되었다 (D-033).
- **Phase 5에서 Karpenter를 뺐다.** 관리형 노드그룹이 이미 돌고 있고, 오버프로비저닝 pause Pod가 노드 대기를 이미 0으로 만든다. 그 위에 Karpenter를 얹으면 Phase 6에서 무엇이 스케일링을 만들었는지 분리가 안 된다. 노드 확보가 실제 병목으로 측정되면 그때 넣는다.

**Phase 4가 결정적이다.** Pod 1개당 WebSocket 커넥션 수와 RPS를 측정하기 전에는 HPA 임계값도 Karpenter 인스턴스 타입도 추측이다. 이 숫자 없이 Phase 5를 시작하면 전부 재작업이다.

### 10.2 결정 시점 원칙

인프라 구성요소는 **변경 비용**을 기준으로 나눈다.

| 지금 정할 것 | 나중에 정할 것 |
|---|---|
| DB 엔진 (MySQL) | 인스턴스 클래스 |
| 스토리지 암호화 | 스토리지 크기 |
| DB 서브넷 그룹 배치 | Multi-AZ 전환 |
| 문자셋·콜레이션 | 파라미터 그룹 값 |
| 동시성 제어 방식 | 백업 보존 기간 |
| 시크릿 네이밍 규약 | HPA 임계값 |

"스펙 전부 확정 → 인프라 전부 구성"이라는 워터폴은 틀렸다. **인터페이스 계약 확정 → 인프라 골격 → 사이징은 측정 후**가 맞다.

### 10.3 Terraform 모듈 분리

> **v1.1 정정.** 아래 번호 체계는 채택하지 않는다. 저장소가 이미 다른 규약으로
> 돌고 있고 근거도 남아 있다(저장소 `docs/decisions.md` D-002). 계층 간 참조도
> `terraform_remote_state`로 이미 동작 중이므로 SSM으로 바꾸지 않는다.
> **실제 구조는 아래와 같다.**
>
> ```
> infra/
> ├── 00-cicd/         # GitHub OIDC, IAM Role, ECR
> ├── 01-network/      # VPC, Subnet, NAT           (거의 안 건드림)
> ├── 02-eks/          # 클러스터, 노드그룹, 애드온
> ├── 03-data/         # RDS, Valkey, SQS           (backend key = datastore/)
> ├── 04-platform/     # Argo CD, LBC, ESO          (CI에서 plan 안 함)
> ├── 05-datadog/      # Datadog 대시보드
> ├── 06-agent/        # Dify 호스트                 (D-028)
> ├── 06-datastream/   # 백데이터 파이프라인          (D-029, backend key = data/)
> └── 07-media/        # MediaMTX용 CloudFront, NLB  (미작성, D-033)
> ```
>
> 번호는 **의존 순서**다. apply는 `01` → `02` → (`03` ∥ `05` ∥ `06` ∥ `07`) → `04` 이고 로컬에서 한다.

원문(v1.0)의 제안은 다음과 같았다. 원칙 — "`20-data`만 독립적으로 destroy/apply 가능해야 실험 비용을 통제할 수 있다" — 는 그대로 유효하며 `03-data`가 그 역할을 한다.

```
terraform/
├── 00-network/      # VPC, Subnet, NAT      (거의 안 건드림)
├── 10-cluster/      # EKS, Karpenter        (드물게 변경)
├── 20-data/         # RDS, ElastiCache      (자주 apply/destroy)
├── 30-platform/     # ESO, Gateway API, Argo CD
└── 40-app/          # 애플리케이션 리소스
```

```hcl
# 00-network/outputs.tf
resource "aws_ssm_parameter" "private_subnet_ids" {
  name  = "/infra/${var.env}/network/private_subnet_ids"
  type  = "StringList"
  value = join(",", module.vpc.private_subnets)
}

# 20-data/main.tf
data "aws_ssm_parameter" "private_subnet_ids" {
  name = "/infra/${var.env}/network/private_subnet_ids"
}
```

**보안 그룹 순환 참조 주의.** EKS 노드 SG와 RDS SG를 서로 참조하면 Terraform 순환 의존이 발생한다. `aws_security_group_rule`을 별도 리소스로 분리한다.

---

## 11. 리스크 레지스터

v1.1에서 최상단 3건이 바뀌었다. R-19~R-21은 P0에서 실제로 드러난 것이다.

| ID | 리스크 | 영향 | 완화 |
|---|---|---|---|
| ~~**R-19**~~ | ~~**state 키 충돌**~~ | 해소됨. `03-data` 는 `datastore/`, `06-datastream` 은 `data/` 로 갈렸다 (D-029) | 키 규칙은 `AGENTS.md` 최상단 표에 남겼다 |
| **R-20** | **파트 경계 침범** | 백데이터·데이터 스트림 구성을 커머스 쪽에서 바꾸면 담당 파트의 apply와 충돌 | 연동은 이벤트 스키마 계약까지만. 그 뒤 경로는 담당 파트 소관 |
| **R-21** | **전송량 과금** | Peak 영상 36 TB/시간, 채팅 576 GB/시간 | 부하 테스트 1/10 축소 고정, 영상은 부하 경로에서 제외 |
| **R-22** | 발화율 스파이크 | 팬아웃이 인입 × 동접의 곱이라 제곱으로 반응 | 200ms 배치 + 창당 표시 상한 (9.4-8) |
| **R-23** | MediaMTX 단일 파드 | 축출·크래시 시 방송 중단 | On-Demand 고정, `do-not-disrupt`. HA는 만들지 않음(감수) |
| R-01 | 재연결 폭풍 | 스케일다운이 곧 장애 | 지터 백오프, 점진 드레이닝, cooldown 600s |
| R-02 | Valkey 단일 장애 | 재고 판정 불가 → 판매 중단 | Multi-AZ, 페일오버 시나리오 사전 검증 |
| R-03 | Pub/Sub 유실 | 무효화 누락, 영구 stale | TTL 안전망 병행, 재연결 시 전체 플러시 |
| R-04 | 캐시 스탬피드 | 방송 시작 시 DB 폭주 | 사전 워밍 CronJob + singleflight |
| R-05 | 핫 키 집중 | 단일 노드 CPU 포화 | 로컬 캐시 흡수, 필요 시 키 복제 |
| R-06 | 커넥션 초과 | MySQL 접속 거부 | 풀 상한 5-10, 필요 시 RDS Proxy |
| R-07 | 리플리카 지연 | stale 응답 | 쓰기 직후 경로는 writer 고정 |
| R-08 | Spot 회수 | 방송 중 노드 소실 | 채팅·주문은 On-Demand 고정 |
| R-09 | Consolidation 중단 | 커넥션 대량 끊김 | WhenEmpty + do-not-disrupt |
| R-10 | 로컬 캐시 메모리 누수 | Pod OOM | LRU 엔트리 상한 필수 |
| R-11 | MCP 레이트 리밋 소진 | 에이전트 정지 | 80% 지점 알림, 이벤트 드리븐 설계 |
| R-12 | 프롬프트 인젝션 | 에이전트 오작동 | 로그를 데이터로 취급, 승인 게이트 |
| R-13 | 오판 재학습 | AIOps 정확도 악화 | `human_verified=true`만 인덱싱 |
| R-14 | 비용 폭증 | 개인 계정 부담 | NAT/RDS Budgets 알림, 야간 정지 |
| R-15 | 오버프로비저닝 상시 유지 | 유휴 시간 낭비 | 스케줄 연동으로 replicas 0 |
| R-16 | Cross-AZ 전송 요금 | 예상 밖 비용 | Pod와 Valkey 동일 AZ 우선 배치 |
| R-17 | 캐시 워밍 실패 | 방송 시작 스탬피드 | CronJob 실패 알림 필수 |
| R-18 | 방송 후 재고 미반영 | 데이터 불일치 | 종료 배치 실패 알림 |

---

## 12. 검증 계획

### 12.1 부하 테스트

**두 가지 전제가 있다.**

1. **콜드 캐시 상태에서 시작해야 의미가 있다.** 워밍된 상태로 테스트하면 스탬피드를 잡아내지 못한다.
2. **모든 시나리오는 목표의 1/10 축소로 돌리고, 영상은 경로에서 뺀다** (v1.1). 근거는 3.2 마지막 항목이다. 실제 40,000은 측정하지 않고 축소 결과를 선형 외삽한다.

| 단계 | 실제 CCU | 축소 CCU | 축소 RPS |
|---|---|---|---|
| 평시 | 5,000 | 500 | 50 |
| 프로모션 | 20,000 | 2,000 | 200 |
| Peak | 40,000 | 4,000 | 400 |
| Stress | 50,000 | 5,000 | 500 |

아래 k6 시나리오의 `target`·`rate`는 축소값으로 적어야 한다.

```bash
kubectl exec -it deploy/api -- curl -X POST localhost:8080/admin/cache/flush
valkey-cli -h <endpoint> FLUSHDB
k6 run broadcast-spike.js
```

```javascript
export const options = {
  scenarios: {
    chat: {
      executor: 'ramping-vus',
      exec: 'chatScenario',
      stages: [
        { duration: '30s', target: 10000 },  // 방송 시작 — 30초 내 만재
        { duration: '20m', target: 10000 },  // 유지
        { duration: '2m',  target: 0 },      // 종료 — 재연결 폭풍 관찰
      ],
    },
    flashsale: {
      executor: 'constant-arrival-rate',
      exec: 'orderScenario',
      startTime: '10m',
      duration: '30s',
      rate: 600, timeUnit: '1s',
      preAllocatedVUs: 1000,
    },
  },
};
```

### 12.2 측정 항목

| 항목 | 목표 | 지표 |
|---|---|---|
| Pod당 안정 커넥션 수 | Phase 4 베이스라인 대비 | `ws_active_connections` |
| 스케일업 실제 소요 시간 | 60초 이내 | `kube_deployment_status_replicas_available` |
| 재고 정합성 | 오버셀 0건 | 판매 수량 = 차감 수량 |
| 스케일다운 재연결 성공률 | 99% 이상 | 클라이언트 재연결 로그 |
| 계층별 흡수율 | 3.10 표 참조 | `cache_hit_total{layer=}` |
| MySQL 버퍼 풀 적중률 | 99% 이상 | `Innodb_buffer_pool_*` |
| MCP 툴 콜 사용량 | 월 40,000회 이하 | `datadog.mcp.tool.usage` |

```
sum(rate(cache_hit_total{layer="local"}[1m]))
  / sum(rate(cache_request_total[1m]))
```

### 12.3 핫 키 확인

```bash
valkey-cli --hotkeys
valkey-cli INFO commandstats | sort -t= -k2 -rn | head
# CloudWatch: EngineCPUUtilization을 노드별로 분해
```

### 12.4 인프라 검증

```bash
# RDS 암호화 상태
aws rds describe-db-instances --db-instance-identifier <ID> \
  --query 'DBInstances[0].{Encrypted:StorageEncrypted,KmsKey:KmsKeyId}'

# Pod → RDS 도달성
kubectl run pgcheck --rm -it --image=mysql:8 --restart=Never -- \
  mysql -h <RDS_ENDPOINT> -u <user> -p -e 'SELECT 1'

# Marketplace 요금 분리 확인
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-09-01 \
  --granularity MONTHLY --metrics UnblendedCost \
  --filter '{"Dimensions":{"Key":"BILLING_ENTITY","Values":["AWS Marketplace"]}}'
```

---

## 13. 미결정 사항

v1.0의 미결정 5건 중 3건이 확정됐다. 남은 것과 새로 생긴 것만 적는다.

| ID | 항목 | 영향 범위 | 결정 기한 |
|---|---|---|---|
| ~~D-14~~ | ~~상품 정보 전달~~ | **확정 — WebSocket 푸시 단일화** | v1.1 |
| ~~D-15~~ | ~~채팅 이벤트 다중 소비~~ | **확정 — 불필요, Valkey Pub/Sub만** | v1.1 |
| ~~-~~ | ~~목표 동시 시청자 수~~ | **확정 — 0.1 표 참조** | v1.1 |
| **신규** | 백데이터 파트와의 이벤트 스키마 계약 | 애플리케이션이 발행할 이벤트 형태 | Phase 1 |
| 신규 | 채팅 표시 상한 `MAX_PER_TICK` | 스파이크 시 팬아웃 상한 | Phase 4 (측정) |
| 신규 | Karpenter 도입 여부 | 노드 스케일링 | Phase 6 (측정) |
| 기존 | ElastiCache Serverless vs 노드 기반 | 비용 | Phase 6 (측정 후로 연기) |
| 기존 | 에이전트 조치 권한: 권고만 vs 실행 | 승인 게이트 설계 | Phase 7 |

v1.0의 "D-14가 가장 상위"는 해소됐다. 지금 남은 것들은 대부분 **측정 후 결정**이라 Phase 4·6이 지나야 답이 나온다. Phase 1에서 정할 것은 백데이터 파트와의 이벤트 스키마 계약 하나다 — 애플리케이션 코드에 박히는 것이라 나중에 바꾸면 전 서비스를 고쳐야 한다.

---

## 부록 A. 참고 사항

### A.1 상표

포트폴리오로 실제 브랜드를 클론하는 것 자체는 일반적이나, 로고·상표·실제 상품 이미지를 그대로 사용하면 문제가 될 수 있다. 도메인 모델만 차용하고 브랜딩은 가상으로 둔다. 이력서에는 "뷰티 커머스 도메인 라이브커머스 서비스"로 표기한다.

### A.2 가격 정보의 유효기간

본 문서의 모든 가격은 상대 비교용이며 리전·시점에 따라 변동한다. 도입 직전 아래에서 재확인한다.

- ElastiCache: AWS ElastiCache 요금 페이지
- MSK / Kinesis: 각 서비스 요금 페이지
- Datadog: AWS Marketplace 리스팅 페이지
- 전체: AWS Pricing Calculator

### A.3 개발 기간 비용 통제

```bash
# RDS 야간 정지 (최대 7일 후 자동 재시작됨에 주의)
aws rds stop-db-instance --db-instance-identifier <ID>

# Karpenter NodePool 스케일 다운
kubectl patch nodepool default --type merge -p '{"spec":{"limits":{"cpu":"0"}}}'
```

상대적 비용 크기는 대략 다음 순서다.

```
NAT Gateway ≳ RDS(Multi-AZ) > EKS 컨트롤 플레인 > RDS(Single-AZ) > ElastiCache(t4g.micro) > EBS
```

NAT Gateway가 시간당 요금 + 데이터 처리 요금으로 이중 과금되어 체감상 가장 크게 나오는 경우가 많다.

---

## 부록 B. 확정 스택 요약

```
영상 송출        OBS (송출자 로컬) → RTMP
영상 리패키징     MediaMTX (EKS, 파드 1개, 트랜스코딩 없음)
영상 배포        CloudFront + Origin Shield (HLS)
CDN             CloudFront — 영상·정적 자산 전용. API 캐싱 계층은 없음
클라이언트 전달   WebSocket 푸시 단일 채널 (폴링 없음)
채팅 게이트웨이   Node.js / TypeScript (200ms 배치 + 표시 상한)
로컬 캐시        인프로세스 LRU (TTL 1초, singleflight) — 안전망 역할
분산 캐시        ElastiCache Valkey (Multi-AZ, 클러스터 모드 off)
무효화 채널      Valkey Pub/Sub + TTL 안전망
비동기 큐        SQS Standard (멱등 키)
영속 저장소      RDS MySQL (writer + read replica, 암호화 on)
스트리밍 브로커   없음 (커머스 이벤트는 SQS + Valkey Pub/Sub)
관측            Datadog (AWS Marketplace 경유)
AI 에이전트      Bedrock + AgentCore Gateway + Datadog MCP
백데이터         별도 파트 소관 — 연동은 이벤트 스키마 계약까지 (7장 범위 주석)
오케스트레이션    EKS + KEDA + Argo CD (Karpenter는 Phase 6 판단)
IaC             Terraform (00-cicd / 01-network / 02-eks / 03-data / 04-platform / 05-datadog / 06-agent / 06-datastream / 07-media)
```
