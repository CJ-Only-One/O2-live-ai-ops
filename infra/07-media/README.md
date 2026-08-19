# 07-media

영상 배포용 CloudFront. `/hls` 경로만 통과시킨다.

```
OBS → RTMP:1935 → NLB → MediaMTX → HLS → ALB → CloudFront → 브라우저
                                            ↑ 오리진      ↑ 이 스택
```

## 왜 이 스택만 Terraform 인가

영상 스택의 나머지는 매니페스트가 만든다 (D-033).

| 구성요소 | 만드는 곳 |
|---|---|
| MediaMTX 파드 | `O2-live-deploy/mediamtx-deployment.yaml` |
| NLB (RTMP 인제스트) | `mediamtx-rtmp-service.yaml` 의 `type: LoadBalancer` |
| ALB `/hls` 경로 | `frontend-ingress.yaml` |
| 송출 비밀번호 | `04-platform` 의 `app_events.tf` |
| **CloudFront** | **여기** |

## 선행 조건

`o2/dev/media-cdn-secret` 이 Secrets Manager 에 있어야 한다. 없으면 apply 가
data source 에서 깨진다.

```bash
SECRET=$(openssl rand -hex 24)
aws secretsmanager create-secret --name o2/dev/media-cdn-secret \
  --description "MediaMTX hlsCDNSecret" --secret-string "$SECRET"
```

**같은 값을 MediaMTX 도 알아야 한다.** `04-platform` 이 그 시크릿을 읽어
Secret `o2-media` 에 넣고, 매니페스트가 `MTX_HLSCDNSECRET` 으로 주입한다.

## 캐시가 먹는 조건

MediaMTX 는 플레이리스트와 세그먼트 주소에 **시청자별 세션 ID** 를 붙인다.
그대로 두면 CloudFront 가 전부 다른 객체로 보고 캐시가 한 번도 안 맞는다 —
시청자 수만큼 오리진을 치게 되어 "파드 하나로 40,000명" 이 무너진다.

CloudFront 가 오리진 요청에 `Authorization: Bearer <시크릿>` 을 붙이면
MediaMTX 가 CDN 요청으로 판정해 세션 ID 를 붙이지 않는다.

```
헤더 없이     main_stream.m3u8?session=17286727-...
Bearer 붙임   main_stream.m3u8
```

**어긋나도 재생은 된다.** 캐시만 조용히 안 먹는다. 근거와 실측은
[D-038](../../docs/decisions.md).

## 캐시 정책이 둘인 이유

| 대상 | TTL | 근거 |
|---|---|---|
| `.m3u8` | 1~2초 | 2초마다 내용이 바뀐다. 세그먼트 길이보다 짧아야 재생이 안 끊긴다 |
| `.ts` | 1년 | 파일명이 콘텐츠 해시라 내용이 바뀌면 이름이 바뀐다. 무효화가 불필요하다 |

## 적용

```bash
terraform init
terraform apply
```

배포 생성에 10~15분 걸린다. 끝나면 출력의 `hls_base_url` 을 `04-platform` 의
`hls_base_url` 변수에 넣고 apply 한 뒤, api 파드를 재시작하고 시드를 다시
돌린다 — `broadcasts.hls_url` 이 그때 바뀐다.

## 비용

유휴 시 $0 이다. 시간당 요금이 없고 요청과 전송량으로만 과금한다.

시청자 1명이 1시간 보면 약 $0.14 (2.5 Mbps 기준 1.1 GB + 요청 3,600건).

**부하 테스트에 영상을 넣지 않는다.** 축소 목표인 4,000명으로도 시간당 4.4 TB,
약 $530 이다. 부하가 CloudFront 로 가고 우리 파드에 닿지 않아 얻는 정보도 없다
(`architecture.md` R-21).
