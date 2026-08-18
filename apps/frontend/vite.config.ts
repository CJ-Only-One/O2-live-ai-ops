import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * 개발 서버가 클러스터와 같은 모양을 흉내낸다.
 *
 * 배포에서는 ALB 하나가 /api 는 api 로, /ws 는 chat-gateway 로 보낸다.
 * 로컬에서도 같은 경로를 쓰려면 프록시가 필요하다 — 그래야 코드에 개발용
 * 분기가 생기지 않고, WebSocket 이 location.host 를 그대로 쓸 수 있다.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.WS_TARGET ?? 'http://localhost:8090',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
