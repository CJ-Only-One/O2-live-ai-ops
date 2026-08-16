import { Route, Routes } from 'react-router-dom'

import LiveLobby from './pages/LiveLobby'
import LiveRoom from './pages/LiveRoom'
import OrderStatus from './pages/OrderStatus'
import DebugPage from './pages/DebugPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LiveLobby />} />
      {/* 계약의 식별자 이름을 그대로 쓴다 (contracts.md 1.2). */}
      <Route path="/live/:broadcastId" element={<LiveRoom />} />
      <Route path="/orders/:orderId" element={<OrderStatus />} />
      <Route path="/debug" element={<DebugPage />} />
    </Routes>
  )
}

export default App
