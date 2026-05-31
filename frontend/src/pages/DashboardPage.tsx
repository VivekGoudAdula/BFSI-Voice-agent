import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { BarChart } from '../components/common/BarChart'
import { PageHeader } from '../components/common/PageHeader'
import { StatCard } from '../components/common/StatCard'
import type { DashboardSummary } from '../types'
import { formatDate } from '../utils/format'

export function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.getDashboard())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [load])

  if (loading && !data) {
    return <div className="page"><p className="loading">Loading dashboard…</p></div>
  }

  const d = data!

  return (
    <div className="page">
      <PageHeader
        title="Dashboard"
        subtitle="Platform overview and recent activity"
        actions={
          <button type="button" className="btn btn-secondary" onClick={load}>
            Refresh
          </button>
        }
      />

      <div className="stat-grid">
        <StatCard label="Total Calls" value={d.total_calls} accent="#3b82f6" />
        <StatCard label="Active Campaigns" value={d.active_campaigns} accent="#8b5cf6" />
        <StatCard label="Completed Calls" value={d.completed_calls} accent="#22c55e" />
        <StatCard label="Escalations" value={d.escalations} accent="#ef4444" />
        <StatCard label="Callbacks" value={d.callbacks} accent="#f59e0b" />
        <StatCard label="Agents" value={d.agents} accent="#06b6d4" />
        <StatCard label="Customers" value={d.customers} accent="#6366f1" />
        <StatCard label="Live Calls" value={d.live_calls} accent="#ec4899" />
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Call Success Rate</h2>
          <div className="success-ring">
            <span className="success-value">{d.call_success_rate}%</span>
          </div>
          <BarChart
            data={[
              { label: 'Completed', value: d.completed_calls, color: '#22c55e' },
              { label: 'Total', value: d.total_calls, color: '#3b82f6' },
              { label: 'Escalations', value: d.escalations, color: '#ef4444' },
            ]}
          />
        </div>

        <div className="card">
          <h2>Recent Activity</h2>
          {d.recent_activity.length === 0 ? (
            <p className="empty">No recent activity</p>
          ) : (
            <ul className="activity-list">
              {d.recent_activity.map((item) => (
                <li key={`${item.type}-${item.id}`} className={`activity-item activity-${item.type}`}>
                  <div>
                    <strong>{item.title}</strong>
                    {item.description && <span>{item.description}</span>}
                  </div>
                  <time>{formatDate(item.timestamp)}</time>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="quick-links">
        <Link to="/live-calls" className="quick-link">View Live Calls →</Link>
        <Link to="/campaigns" className="quick-link">Manage Campaigns →</Link>
        <Link to="/escalations" className="quick-link">Escalation Queue →</Link>
      </div>
    </div>
  )
}
