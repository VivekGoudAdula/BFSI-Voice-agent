import { NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '◫' },
  { to: '/customers', label: 'Customers', icon: '◎' },
  { to: '/campaigns', label: 'Campaigns', icon: '▤' },
  { to: '/agents', label: 'Agents', icon: '◉' },
  { to: '/live-calls', label: 'Live Calls', icon: '●' },
  { to: '/call-history', label: 'Call History', icon: '☰' },
  { to: '/escalations', label: 'Escalations', icon: '⚠' },
  { to: '/compliance', label: 'Compliance', icon: '✓' },
  { to: '/analytics', label: 'Analytics', icon: '▥' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

export function AdminLayout() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    api.healthCheck()
      .then(() => setOnline(true))
      .catch(() => setOnline(false))
    const interval = setInterval(() => {
      api.healthCheck()
        .then(() => setOnline(true))
        .catch(() => setOnline(false))
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="admin-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">ABC</div>
          <div>
            <strong>Voice Agent</strong>
            <span>Admin Portal</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `nav-link${isActive ? ' active' : ''}`
              }
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className={`status-dot ${online === false ? 'offline' : ''}`} />
          {online === null ? 'Connecting…' : online ? 'Backend online' : 'Backend offline'}
        </div>
      </aside>
      <div className="admin-main">
        <Outlet />
      </div>
    </div>
  )
}
