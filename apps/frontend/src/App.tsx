import { Route, Routes } from 'react-router-dom'
import LiveLobby from './pages/LiveLobby'
import LiveRoom from './pages/LiveRoom'
import Checkout from './pages/Checkout'
import DebugPage from './pages/DebugPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LiveLobby />} />
      <Route path="/live/:liveId" element={<LiveRoom />} />
      <Route path="/checkout/:productId" element={<Checkout />} />
      <Route path="/debug" element={<DebugPage />} />
    </Routes>
  )
}

export default App
