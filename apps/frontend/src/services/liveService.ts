import { mockLives } from '../mocks/lives'
import type { LiveItem } from '../types'

// 프론트만 먼저 만드는 단계라 실제 GET /api/lives 대신 mock을 쓴다.
// 나중에 live-api가 준비되면 이 안쪽만 fetch(`${API_BASE_URL}/lives`)로 바꾸면 된다.
const DELAY_MS = 250

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), DELAY_MS))
}

export function fetchLives(): Promise<LiveItem[]> {
  return delay(mockLives)
}

export function fetchLiveById(id: string): Promise<LiveItem | undefined> {
  return delay(mockLives.find((live) => live.id === id))
}
