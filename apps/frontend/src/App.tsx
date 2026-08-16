import { Route, Routes } from 'react-router-dom'

import Splash from './components/Splash'
import Home from './pages/Home'
import LiveLobby from './pages/LiveLobby'
import LiveRoom from './pages/LiveRoom'
import OrderStatus from './pages/OrderStatus'
import DebugPage from './pages/DebugPage'

function App() {
  return (
    <>
      {/* 앱 진입 스플래시. 데이터를 기다리지 않고 화면만 덮는다. */}
      <Splash />
      <Routes>
        <Route path="/" element={<Home />} />
        {/* 올영LIVE 전체보기. 홈의 라이브 섹션에서 들어온다. */}
        <Route path="/live" element={<LiveLobby />} />
        {/* 계약의 식별자 이름을 그대로 쓴다 (contracts.md 1.2). */}
        <Route path="/live/:broadcastId" element={<LiveRoom />} />
        <Route path="/orders/:orderId" element={<OrderStatus />} />
        <Route path="/debug" element={<DebugPage />} />
      </Routes>
    </>
  )
}

export default App
