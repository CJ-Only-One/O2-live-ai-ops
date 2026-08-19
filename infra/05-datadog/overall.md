# AIOps Data Engineering Architecture Context

> **낡은 문서다. 판단 근거로 쓰지 않는다.**
>
> 백데이터 파트가 이 저장소로 코드를 넘기기 전에 쓴 문맥 스냅샷이다.
> 어느 문서도 이 파일을 가리키지 않고, 내용이 저장소의 결정과 어긋난다.
>
> - 5절 `Next Steps for Claude Agent` — **이미 끝난 일이다.** 지시로 읽지 않는다
> - Dify 기동 경로(API Gateway → Lambda)는 D-028·D-031 이후 다시 정하는 중이다
> - Warm Path 의 현재 사실은 `infra/06-datastream/warm/README.md`
>
> 남겨 두는 이유는 그쪽 파트가 무엇을 의도했는지 되짚을 때뿐이다.

## 1. Project Overview
* **목표:** 라이브 커머스 특가 이벤트 등 대규모 트래픽 환경에서 발생하는 비즈니스 장애(인시던트)를 실시간으로 감지하고 대응하는 AI Agent(AIOps) 워크플로우 및 데이터 파이프라인 구축.
* **핵심 철학:** 인시던트의 정의는 인프라 지표가 아닌 '고객 경험(CX) 및 비즈니스 임팩트'를 기준으로 Top-down 방식으로 정의함. AI Agent는 판단을 위해 '사전 집계된 맥락(Warm Data)'과 '원본 데이터(Cold Data)', '과거 노하우(RAG)'를 분리하여 활용함.

## 2. Data Pipeline Architecture (3-Tier Path)
현재 인프라는 AWS 위에서 동작하며, 다음 세 가지 패스로 완벽히 분리되어 설계 및 구축됨.

### 2.1 Hot Path (Trigger & Alert)
* **컴포넌트:** Datadog
* **역할:** 시스템의 얕은 지표를 실시간으로 모니터링하여 임계치 초과 시 Webhook을 통해 AI Agent를 기동(Trigger)시키는 방아쇠 역할.
* **특징:** 고(High) 카디널리티 데이터 처리에 따른 비용 폭탄을 방지하기 위해 가벼운 숫자 형태의 커스텀 메트릭(예: `custom.macro_sniper_ratio`)만 수신함.

### 2.2 Warm Path (AI Context - Real-time)
* **컴포넌트:** Kinesis -> Lambda (`o2-agg`, 10s Window Batching) -> DynamoDB (`o2-agent-context`)
* **역할:** AI Agent가 즉각적인 1차 진단(응급처치)을 내리기 위해 읽어들이는 실시간 비즈니스 맥락(Context) 저장소.
* **데이터 구조 (JSON):** 
  * 식별자 (PK/SK, Window)
  * 복합 지표 (예: `checkout_to_inventory_ratio`)
  * 고(High) 카디널리티 정보 (예: 에러가 집중된 Top 5 상품 ID, 악성 IP 배열 등)
  * 상태 플래그 (`is_frontend_spiky` 등)
* **설계 이유:** Prometheus/Grafana(TSDB)가 처리하지 못하는 복잡한 스트림 조인과 고 카디널리티 텍스트 데이터를 LLM이 소비하기 좋은 JSON 문서 형태로 제공하기 위함.

### 2.3 Cold Path (Deep Dive & RCA - Delayed)
* **컴포넌트:** Kinesis Firehose (300s 버퍼링) -> S3 (`raw` bucket) -> Glue Job -> S3 (`ml-ready` bucket, Parquet 포맷)
* **역할:** AI Agent가 1차 지혈 후(약 5분 뒤) 심층 원인 분석(Deep Dive)을 위해 쿼리하는 정형화된 팩트 데이터.
* **활용 방식:** RAG용 Vector DB에 넣는 것(안티패턴)이 아니라, AI Agent가 **Text-to-SQL (Athena Tool Calling)**을 사용하여 명확한 조건(IP, 앱 버전 등)으로 조회함. Parquet 포맷을 사용하여 쿼리 비용 및 속도를 최적화하고 민감 정보(PII)를 마스킹함.

## 3. AI Agent (Dify) Workflow
장애 발생 시 AI Agent의 행동 프로세스:
1. **기동:** Datadog Webhook -> AWS API Gateway -> Lambda(Incident Handler) -> Dify API 호출
2. **1차 진단 (0~1분):** DynamoDB(Warm Data)를 조회하여 비즈니스 맥락 파악.
3. **지식 검색:** Vector DB(RAG)를 검색하여 과거 유사 인시던트의 런북(Runbook) 및 사후 분석서(Post-mortem) 참조.
4. **1차 조치:** WAF IP 차단, 서킷 브레이커 발동 등 긴급 지혈 및 슬랙 보고.
5. **심층 진단 (5분 후):** Cold Data(S3 `ml-ready`)에 Athena 쿼리 도구를 사용하여 정확한 통계 기반의 근본 원인 도출 및 엔지니어용 리포트 발송.

## 4. Current Infrastructure Status (Terraform Applied)
사용자는 `warm-path.tf`, `lambda.tf`, `dynamodb.tf`, `s3.tf`, `glue.tf`, `irsa.tf` 등을 활용하여 핵심 인프라 스트럭처 생성을 완료함.
* Kinesis, Firehose, S3, Glue, Lambda, DynamoDB 및 IAM(IRSA) 역할이 성공적으로 배포됨.
* 다양한 Smoke Test 스크립트로 파이프라인 검증 체계 확보 완료.

## 5. Next Steps for Claude Agent
* **목표 1:** 배포된 AWS 인프라 위에 Datadog Integration을 위한 Terraform 코드(`datadog.tf`, `datadog_webhook`, `datadog_monitor`) 추가 작성 및 반영.
* **목표 2:** Datadog Webhook 페이로드를 수신하여 Dify API 형식에 맞게 파싱 및 전달하는 미들웨어 (API Gateway + Incident Handler Lambda) 인프라 및 코드 구현.
* **목표 3:** `warm/handlers/aggregate.py` 내부에 `Macro_Sniper_Ratio` 등 비즈니스 팀과 합의한 Warm Path 지표 집계 로직(스트림 조인) 파이썬 코드 완성.