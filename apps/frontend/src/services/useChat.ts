/**
 * 채팅 WebSocket (contracts.md 3).
 *
 * EventSource(SSE) 의 내장 재연결을 쓰지 않는 이유는 거기에 지터가 없기
 * 때문이다. 파드가 줄어드는 순간 끊긴 연결이 전부 같은 시각에 재접속하면
 * 남은 파드가 그 자리에서 죽는다 (리스크 R-01).
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { sessionKey } from './api'
import type { ChatItem } from '../types'

/** 화면에 유지할 메시지 수. 무제한이면 긴 방송에서 브라우저가 무거워진다. */
const MAX_VISIBLE = 100

/** 하트비트. ALB 유휴 타임아웃보다 짧아야 조용한 커넥션이 안 끊긴다. */
const PING_INTERVAL_MS = 30_000

function wsUrl(broadcastId: string): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws?broadcast_id=${encodeURIComponent(broadcastId)}`
}

/**
 * 지터를 넣은 지수 백오프.
 *
 *   대기 = min(30s, 2^n초) × (0.5 + random() × 0.5)
 *
 * 지터가 없으면 40,000 개가 같은 순간에 재접속한다 (contracts.md 3.6).
 */
function backoffMs(attempt: number): number {
  const base = Math.min(30_000, 2 ** attempt * 1000)
  return base * (0.5 + Math.random() * 0.5)
}

export function useChat(broadcastId: string | undefined) {
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [connected, setConnected] = useState(false)

  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!broadcastId) return

    /**
     * 이 이펙트만의 플래그다. ref 로 공유하면 안 된다 — 이전 이펙트가 만든
     * 소켓의 onclose 가 나중에 도착할 때 그 값은 이미 새 이펙트가 false 로
     * 되돌려놓은 뒤라, 죽은 소켓이 재연결을 예약한다. 그러면 연결이 계속
     * 늘어난다. StrictMode 의 이중 실행에서 이것이 바로 드러난다.
     */
    let cancelled = false
    let attempt = 0
    const timers: number[] = []

    const connect = () => {
      if (cancelled) return

      // 토큰을 쿼리스트링이 아니라 서브프로토콜로 보낸다.
      // 쿼리스트링은 ALB 접근 로그에 남는다 (contracts.md 3.1).
      const socket = new WebSocket(wsUrl(broadcastId), [sessionKey()])
      socketRef.current = socket

      socket.onopen = () => {
        if (cancelled) {
          socket.close()
          return
        }
        setConnected(true)
        attempt = 0

        const ping = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ t: 'ping' }))
          }
        }, PING_INTERVAL_MS)
        timers.push(ping)
      }

      socket.onmessage = (event) => {
        if (cancelled) return
        // 서버 프레임은 단건이어도 항상 배열이다 (contracts.md 3.2).
        const frame = JSON.parse(event.data) as { t: string; items: unknown[] }
        if (frame.t !== 'chat') return
        setMessages((prev) => [...prev, ...(frame.items as ChatItem[])].slice(-MAX_VISIBLE))
      }

      socket.onclose = () => {
        if (cancelled) return
        setConnected(false)

        const timer = window.setTimeout(connect, backoffMs(attempt++))
        timers.push(timer)
      }

      // 오류 뒤에는 close 가 이어지므로 재연결은 onclose 한 곳에서만 건다.
      socket.onerror = () => socket.close()
    }

    connect()

    return () => {
      cancelled = true
      timers.forEach(clearTimeout)
      timers.forEach(clearInterval)
      socketRef.current?.close()
    }
  }, [broadcastId])

  const send = useCallback((text: string) => {
    const msg = text.trim()
    if (!msg) return
    const socket = socketRef.current
    if (socket?.readyState !== WebSocket.OPEN) return
    // 클라이언트 → 서버는 배열이 아니다. 한 번에 하나만 보낸다 (3.4).
    socket.send(JSON.stringify({ t: 'chat', msg }))
  }, [])

  return { messages, connected, send }
}
