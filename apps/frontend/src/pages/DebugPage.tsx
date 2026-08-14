import { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// 파이프라인 연결 확인용 페이지. 실제 라이브커머스 데모와는 별개다.
//
// 예전에는 /items 로 DB 쓰기까지 확인했으나 그 라우트를 지웠다.
// 예제 스키마였고, 계약(docs/contracts.md)에 맞춘 실제 도메인 테이블이
// 들어오면 어차피 사라질 것이었다.
//
// 지금 이 페이지가 확인하는 것은 "브라우저 -> ALB -> api 파드" 경로다.
// DB 연결까지 보려면 /api/readyz 가 생긴 뒤 그것을 부른다.
function DebugPage() {
  const [status, setStatus] = useState('확인 중...')

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((res) => {
        if (!res.ok) throw new Error()
        return res.json()
      })
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('백엔드에 연결하지 못했습니다'))
  }, [])

  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>O2 Debug</h1>
      <p>백엔드 상태: {status}</p>
      <p style={{ color: '#666', fontSize: 13 }}>
        브라우저 → ALB → api 파드 경로만 확인합니다. DB 연결은 포함하지 않습니다.
      </p>
    </div>
  )
}

export default DebugPage
