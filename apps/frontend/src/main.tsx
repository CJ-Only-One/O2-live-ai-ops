// 몰과 같은 조합. 라틴은 Montserrat, 한글은 Noto Sans KR 이 받는다.
// CDN 대신 패키지로 넣어 외부 의존과 로딩 지연을 만들지 않는다.
// Noto Sans KR 은 유니코드 범위별로 쪼개져 있어 필요한 조각만 받는다.
import '@fontsource/montserrat/600.css'
import '@fontsource/montserrat/700.css'
import '@fontsource/montserrat/800.css'
import '@fontsource/noto-sans-kr/400.css'
import '@fontsource/noto-sans-kr/500.css'
import '@fontsource/noto-sans-kr/700.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
