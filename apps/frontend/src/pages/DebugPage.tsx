import { useEffect, useState } from 'react'

import { api } from '../services/api'

/** 백엔드 연결 확인용. 서비스 화면과는 별개다. */
function DebugPage() {
  const [health, setHealth] = useState('확인 중...')
  const [ready, setReady] = useState('확인 중...')

  useEffect(() => {
    api.get<{ status: string }>('/health')
      .then((d) => setHealth(d.status))
      .catch(() => setHealth('연결 실패'))
    // readyz 는 의존성이 끊기면 503 이라 실패도 정보다.
    api.get<{ status: string }>('/readyz')
      .then((d) => setReady(d.status))
      .catch(() => setReady('의존성 연결 실패'))
  }, [])

  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>O2 Debug</h1>
      <p>health (프로세스): {health}</p>
      <p>readyz (MySQL·Valkey): {ready}</p>
    </div>
  )
}

export default DebugPage
