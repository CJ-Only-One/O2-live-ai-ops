import { api } from './api'
import type { Broadcast } from '../types'

/**
 * 방송 진입 스냅샷 (contracts.md 2.1).
 *
 * 이후 변화는 WebSocket 으로 푸시된다 — 폴링하지 않는다. 진입 시 1회 조회만
 * 남기는 것이 D-14 의 요지이고, 그 1회가 방송 시작 순간에 몰리는 것이
 * 캐시 스탬피드다.
 */
export function fetchBroadcast(broadcastId: string): Promise<Broadcast> {
  return api.get<Broadcast>(`/broadcasts/${broadcastId}`)
}

/**
 * 계약에 방송 목록 API 가 없다. 단건 조회만 있으므로 로비가 보여줄 방송은
 * 여기 상수로 둔다. mock 서비스를 만들면 없는 API 가 있는 것처럼 보인다.
 *
 * 목록이 필요해지면 계약에 GET /api/broadcasts 를 추가하고 이 상수를 지운다.
 */
export const KNOWN_BROADCAST_IDS = ['bc_1042', 'bc_1043', 'bc_1050', 'bc_1051', 'bc_1030']
