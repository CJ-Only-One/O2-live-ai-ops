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
      // HLS. 클러스터에서는 같은 ALB 가 /hls 를 MediaMTX 로 보낸다.
      //
      // 로컬에는 MediaMTX 가 없어 기본값을 클러스터 ALB 로 둔다. **이 주소는
      // ALB 를 다시 만들면 낡는다.** 개발 편의용이고, 틀리면 로컬에서 영상만
      // 안 나온다(다른 것은 멀쩡하다). 그때는 HLS_TARGET 으로 덮는다.
      '/hls': {
        target: process.env.HLS_TARGET ?? 'http://k8s-o2dev-frontend-0af27d967f-1008618203.ap-northeast-2.elb.amazonaws.com',
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
