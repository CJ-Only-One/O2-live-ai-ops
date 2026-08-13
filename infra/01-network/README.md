# Network Layer — Team o2

CJ올리브영 올영라이브 장애 시나리오 재현 환경의 AWS 네트워크 기반. EKS 클러스터 및 데이터 계층이 올라갈 토대다.

## 1. 설계 결정 요약

| 결정 | 값 | 근거 |
| --- | --- | --- |
| 리전 | ap-northeast-2 | 대상 서비스가 국내 트래픽. 부하테스트 RTT를 실제와 유사하게 유지. 팀 접근 지연 최소화 |
| AZ 수 | 2 (2a, 2c) | EKS 컨트롤플레인 최소 요건이 2 AZ. 3 AZ로 늘리면 NAT/Endpoint 고정비가 1.5배가 되나, 시나리오 목록에 AZ 장애가 없어 얻는 것이 없다 |
| VPC CIDR | 10.0.0.0/16 | VPC CNI가 Pod마다 VPC IP를 소비. /20 수준이면 노드 스케일아웃 중 IP 고갈로 Pod Pending이 발생 |
| 계층 | public / private-app / private-data 3-tier | 데이터 계층에 0.0.0.0/0 라우트를 아예 두지 않아 라우팅 레벨에서 유출 경로 제거 |
| NAT | 단일 NAT GW (토글) | 3주 테스트. HA로 얻는 가용성 대비 비용이 2배 |
| S3 Gateway Endpoint | 항상 활성 | 요금 0원. ECR 레이어·Loki chunk·Flow Logs 경로를 NAT에서 제외 |
| ECR Interface Endpoint | 기본 비활성 | 손익분기 약 535GB/3주 (아래 계산). S3 GW 활성 시 실제 ECR API 트래픽은 GB 단위에 못 미침 |
| Flow Logs | S3, parquet, 600s | CloudWatch Logs 대비 저렴하고 Athena 직결. 보안·데이터 트랙 입력으로 재사용 |
| State | S3 + `use_lockfile` | Terraform 1.10+ 네이티브 락. DynamoDB 테이블 불필요 |

## 2. CIDR 계획

```
10.0.0.0/16  (65,536)
├─ 10.0.0.0/20    public-a        4,091 usable   ALB/NLB ENI, NAT GW
├─ 10.0.16.0/20   public-c        4,091
├─ 10.0.48.0/22   data-a          1,019          RDS, ElastiCache
├─ 10.0.52.0/22   data-c          1,019
├─ 10.0.64.0/18   private-app-a  16,379          EKS node ENI + Pod ENI
├─ 10.0.128.0/18  private-app-c  16,379
└─ 10.0.192.0/18  (3 AZ 확장 예약)
```

private-app을 /18로 잡은 근거:

- VPC CNI 기본 모드: Pod 1개 = VPC IP 1개
- Prefix Delegation 사용 시 ENI마다 /28(16 IP) 단위로 선점 → 실사용 Pod 수보다 IP 소모가 최대 16배 과할당
- 노드 50대 × ENI 3개 × prefix 2개 × 16 IP ≈ 4,800 IP가 순간 점유될 수 있음
- 서브넷 IP 고갈은 `terraform apply`로 즉시 못 고친다(서브넷 CIDR 확장 불가, 재생성 필요) → 초기에 크게 잡는 것이 유일한 대응

## 3. 비용 분석 (3주 = 504시간 기준)

**요금 근거 상태**

- 확정: NAT GW $0.045/hr + $0.045/GB (us-east-1, AWS 공식 VPC Pricing)
- 추정: ap-northeast-2는 us-east-1 대비 약 1.3배 → **$0.059/hr + $0.059/GB로 가정**. `apply` 전 AWS VPC Pricing 페이지에서 리전 선택해 재확인 필요
- 확정: Gateway Endpoint 요금 0원 (AWS 공식)
- 확정: Interface Endpoint $0.01/hr/AZ + $0.01/GB
- 확정: 퍼블릭 IPv4 $0.005/hr (2024-02 이후 전 리전)

**NAT 구성 비교**

| 구성 | 고정비 (504h) | AZ 장애 영향 | cross-AZ 전송료 |
| --- | --- | --- | --- |
| 단일 NAT GW | 약 $30 | 해당 AZ 다운 시 전체 private egress 중단 | 타 AZ 트래픽에 $0.01/GB/방향 추가 |
| AZ당 NAT GW (2개) | 약 $60 | 해당 AZ만 영향 | 없음 |
| NAT Instance (t4g.micro) | 약 $4 | 단일 장애점, 대역폭 제한 | 없음 |

권장: **단일 NAT GW**. NAT Instance는 $26 절약을 위해 직접 운영·장애 대응 부담을 지는 구조라 3주 일정에서 손해다. 단, Phase 3 부하테스트에서 egress가 커지면 데이터 처리료가 고정비를 넘길 수 있으므로 재평가한다.

**ECR Interface Endpoint 손익분기**

```
고정비  = 2 endpoints × 2 AZ × $0.013/hr × 504h ≈ $26.2
절감액  = ($0.059 - $0.010)/GB = $0.049/GB
손익분기 = 26.2 / 0.049 ≈ 535 GB (3주간 ECR 트래픽)
```

이미지 레이어 실체는 S3에서 내려오므로 S3 Gateway Endpoint를 켜면 ECR api/dkr로 흐르는 것은 매니페스트와 인증 토큰뿐이다. 535GB에 도달할 수 없다. → **비활성이 정답.**
(예외: private-app 서브넷에서 인터넷 egress를 완전히 차단하는 보안 요건이 생기면 비용과 무관하게 켜야 한다.)

**네트워크 계층 총합 추정**

| 항목 | 추정 |
| --- | --- |
| NAT GW 고정비 | $30 |
| NAT 데이터 처리 (200GB 가정) | $12 |
| NAT EIP 퍼블릭 IPv4 | $3 |
| Flow Logs 전달 + S3 저장 | $5-15 (부하테스트 볼륨에 민감) |
| **합계** | **약 $50-60 / 예산 $1,400의 4%** |

네트워크는 예산의 병목이 아니다. 병목은 워커 노드와 EKS 컨트롤플레인($0.10/hr × 504h = $50)이다.

## 4. 검증 방법

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

apply 후 확인:

```bash
# 1. CIDR 겹침/할당 확인
terraform output subnet_cidr_plan

# 2. private 서브넷 egress 경로 확인 (0.0.0.0/0 → nat-*)
aws ec2 describe-route-tables \
  --filters "Name=tag:Name,Values=o2-dev-rt-private-app-*" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`]' --output table

# 3. data 서브넷에 0.0.0.0/0 라우트가 없어야 정상
aws ec2 describe-route-tables \
  --filters "Name=tag:Name,Values=o2-dev-rt-private-data-*" \
  --query 'RouteTables[].Routes[].DestinationCidrBlock' --output table

# 4. S3 Gateway Endpoint가 private RT에 붙었는지
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-endpoint-type,Values=Gateway" \
  --query 'VpcEndpoints[].{Svc:ServiceName,RTs:RouteTableIds}' --output json

# 5. EKS 서브넷 discovery 태그
aws ec2 describe-subnets --filters "Name=tag:Tier,Values=private-app" \
  --query 'Subnets[].Tags[?starts_with(Key,`kubernetes.io`)]' --output json

# 6. 실제 egress 소통 확인 (EKS 올린 뒤)
kubectl run netcheck --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -o /dev/null -w '%{http_code}\n' https://registry.k8s.io/v2/
```

## 5. 리스크

| 리스크 | 발생 조건 | 완화 |
| --- | --- | --- |
| 단일 NAT AZ 장애 | ap-northeast-2a 장애 | `single_nat_gateway=false`로 5분 내 전환 가능하도록 RT를 AZ별로 미리 분리해 둠 |
| 서브넷 IP 고갈 | Pod 수 급증 + prefix delegation | /18 확보. 그래도 부족하면 100.64.0.0/16 secondary CIDR + CNI custom networking |
| Flow Logs 비용 폭증 | 부하테스트 중 ALL 수집 | Phase 3 진입 전 `flow_logs_traffic_type=REJECT` 전환 또는 라이프사이클 단축 |
| NAT 데이터 처리료 폭증 | 부하 생성기를 클러스터 외부에 두면 응답이 egress로 나감 | k6/Locust를 클러스터 내부에 배치하거나 별도 VPC + 퍼블릭 서브넷 배치 |
| 리소스 미삭제 | 프로젝트 종료 후 NAT/EIP 잔존 | 8/28 이후 `terraform destroy`. Budgets 알람 별도 설정 |
| AZ 이름-ID 매핑 불일치 | 팀원이 다른 계정에서 apply | az_id로 재검증 |

## 6. 다음 단계

1. 이 스택 apply → outputs 확인
2. EKS 스택 신규 디렉터리에서 `terraform_remote_state`로 이 outputs 참조
3. Security Group은 EKS 스택 쪽에서 정의 (네트워크 스택은 경계만 담당)
