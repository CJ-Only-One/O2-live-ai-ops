import { useLocation, useNavigate } from 'react-router-dom'

import './TabBar.css'

/**
 * 하단 탭바.
 *
 * 홈과 라이브만 실제로 이동한다. 나머지는 표시용이다 — 카테고리·검색·마이는
 * 이 프로젝트의 범위 밖이고, 없으면 화면이 앱처럼 보이지 않는다.
 */
const TABS = [
  { icon: '🏠', label: '홈', path: '/' },
  { icon: '☰', label: '카테고리', path: null },
  { icon: '📺', label: '라이브', path: '/live' },
  { icon: '🔍', label: '검색', path: null },
  { icon: '👤', label: '마이', path: null },
]

function TabBar() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  return (
    <nav className="tabbar">
      {TABS.map((t) => {
        const active = t.path === pathname
        return (
          <button
            key={t.label}
            className={`tabbar__item${active ? ' is-active' : ''}`}
            onClick={() => t.path && navigate(t.path)}
            disabled={!t.path}
          >
            <span className="tabbar__icon">{t.icon}</span>
            <span className="tabbar__label">{t.label}</span>
          </button>
        )
      })}
    </nav>
  )
}

export default TabBar
