/**
 * 서버 호출 공통부.
 *
 * VITE_API_BASE_URL 은 빌드 시점에 번들에 박힌다. CI 가 '/api' 를 넣으므로
 * 프론트와 api 가 같은 ALB 를 쓰고 도메인을 몰라도 된다.
 */

import type { ApiErrorBody, ErrorCode } from '../types'
import { uuid } from '../utils/uuid'

// 상대 경로가 기본이다. 배포에서는 ALB 가, 로컬에서는 vite 프록시가
// 같은 오리진에서 /api 를 받아 넘긴다. 절대 주소를 기본값으로 두면
// 개발과 배포에서 코드가 갈린다.
const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** 계약의 오류 봉투를 그대로 옮긴 것. code 로 분기한다. */
export class ApiError extends Error {
  // 생성자 파라미터 프로퍼티를 쓰지 않는다. tsconfig 의 erasableSyntaxOnly 가
  // 타입만 지워서 실행 가능한 문법을 요구하는데, 그 축약형은 런타임 코드를
  // 만들어내므로 허용되지 않는다.
  readonly code: ErrorCode
  readonly status: number

  constructor(code: ErrorCode, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })

  if (!res.ok) {
    // 계약이 정한 봉투가 아닐 수도 있다(프록시 오류, 502 등).
    // 그때도 화면이 죽지 않게 INTERNAL_ERROR 로 떨어뜨린다.
    let body: ApiErrorBody | null = null
    try {
      body = await res.json()
    } catch {
      body = null
    }
    throw new ApiError(
      body?.error?.code ?? 'INTERNAL_ERROR',
      body?.error?.message ?? '요청을 처리하지 못했습니다',
      res.status,
    )
  }

  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown, headers?: Record<string, string>) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body), headers }),
}

/**
 * 데모 세션 키. 로그인이 없으므로 브라우저가 만들어 들고 있는다.
 * 서버는 이 값을 그대로 저장하지 않고 HMAC 으로 바꿔 이벤트 봉투에 담는다.
 */
export function sessionKey(): string {
  const KEY = 'o2-session-key'
  let value = localStorage.getItem(KEY)
  if (!value) {
    value = uuid()
    localStorage.setItem(KEY, value)
  }
  return value
}
