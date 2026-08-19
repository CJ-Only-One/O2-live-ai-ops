# apps/frontend

React 19 + TypeScript + Vite. 방송 시청 화면과 주문 흐름.
빌드 결과는 nginx 이미지로 감싸 배포한다 (`Dockerfile`, `nginx.conf`).

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # tsc -b && vite build
npm run lint     # oxlint
```

`5173` 은 `apps/api` 의 `ALLOWED_ORIGINS` 기본값과 짝이다. 포트를 바꾸면
API 의 CORS 도 같이 바꾼다.

## 서버와의 규격

**전부 `docs/contracts.md` 에 있다.** 여기에 옮겨 적지 않는다.

| 무엇 | 절 |
|---|---|
| 방송 진입 스냅샷, 주문 | 2 |
| WebSocket 프레임 포맷·재연결 | 3 |
| 오류 `code` 체계 | 1.3 |

상태 변화는 폴링하지 않는다. 전부 WebSocket 으로 밀어준다
(`architecture.md` D-14).

계약에 맞춘 전면 수정은 아직 끝나지 않았다 — `decisions.md` D-019.
