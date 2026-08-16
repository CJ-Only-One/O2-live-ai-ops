/**
 * UUID v4.
 *
 * crypto.randomUUID 를 직접 쓰지 않는다. 그것은 보안 컨텍스트(HTTPS 또는
 * localhost)에서만 존재하고, 그 밖에서는 undefined 다. 도메인이 붙기 전의
 * ALB 는 HTTP 라 화면이 통째로 뜨지 않는다 — 로컬은 localhost 라 보안
 * 컨텍스트로 취급되므로 개발 중에는 절대 드러나지 않는 종류의 오류다.
 *
 * 멱등키와 세션 키에 쓰이므로 값의 유일성만 지키면 되고, 암호학적 강도는
 * 요구되지 않는다.
 */
export function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  // getRandomValues 는 보안 컨텍스트가 아니어도 대부분 존재한다.
  const bytes = new Uint8Array(16)
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes)
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  }

  // v4 규격: 버전과 변형 비트를 고정한다.
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
