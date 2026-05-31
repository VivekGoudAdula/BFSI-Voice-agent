import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { PageHeader } from '../components/common/PageHeader'
import type { ActiveCall } from '../types'
import { formatDuration } from '../utils/format'

export function LiveCallsPage() {
  const [calls, setCalls] = useState<ActiveCall[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setCalls(await api.getActiveCalls())
    } catch {
      setCalls([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 3000)
    return () => clearInterval(interval)
  }, [load])

  return (
    <div className="page">
      <PageHeader
        title="Live Calls"
        subtitle="Real-time view of active call sessions"
        actions={
          <span className="live-indicator">
            <span className="status-dot pulse" /> Auto-refresh 3s
          </span>
        }
      />

      <div className="card">
        {loading && calls.length === 0 ? (
          <p className="loading">Loading live calls…</p>
        ) : calls.length === 0 ? (
          <div className="empty-state">
            <p className="empty">No active calls right now</p>
            <p className="text-muted">Calls appear here when customers are connected via Twilio Media Streams.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Duration</th>
                  <th>Current Agent</th>
                  <th>Current State</th>
                  <th>Call ID</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.call_id} className="live-row">
                    <td>
                      <strong>{call.customer_name}</strong>
                      <div className="text-muted mono">{call.customer_id.slice(-8)}</div>
                    </td>
                    <td className="mono live-duration">{formatDuration(call.duration_seconds)}</td>
                    <td>{call.agent_name || call.agent_id || '—'}</td>
                    <td>
                      <span className="badge badge-in-progress">{call.current_state}</span>
                    </td>
                    <td className="mono">{call.call_id.slice(-8)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
