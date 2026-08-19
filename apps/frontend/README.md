# frontend

올리브영 라이브 화면. React + TypeScript + Vite.

```bash
npm install
npm run dev     # localhost:5173. /api 와 /ws 는 vite.config.ts 가 프록시한다
npm run build
npm run lint
```

개발 서버는 `/api` 를 `localhost:8000`, `/ws` 를 `localhost:8090` 으로 보낸다
(`API_TARGET` · `WS_TARGET` 로 바꿀 수 있다). 클러스터에서는 ALB 하나가 같은
경로를 나눠 보내므로 코드에 개발용 분기가 없다.

## 알아둘 것

- **서버 응답 형태는 `docs/contracts.md` 를 따른다.** `src/types.ts` 가 그 사본이고,
  어긋나면 화면이 조용히 빈 값을 그린다. 이름을 바꾸려면 계약 문서를 먼저 고친다.
- **`src/presentation.ts` 는 서버가 주지 않는 값이다.** 제목·썸네일·브랜드·예고
  문구처럼 틀려도 사고가 나지 않는 것만 둔다. 여기 값으로 주문 가부나 금액을
  판단하지 않는다.
- 이미지는 `public/` 의 SVG 다. 실제 사진으로 바꾸려면 같은 이름으로 파일을 넣고
  `presentation.ts` 의 확장자만 고친다.
