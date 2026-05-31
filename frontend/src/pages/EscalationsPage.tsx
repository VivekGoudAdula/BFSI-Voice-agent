import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { PageHeader } from '../components/common/PageHeader'
import type { Escalation, HandoffQueueItem } from '../types'
import { formatDate, statusBadge } from '../utils/format'

export function EscalationsPage() {
  const [escalations, setEscalations] = useState<Escalation[]>([])
  const [queue, setQueue] = useState<HandoffQueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'escalations' | 'queue'>('queue')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [e, q] = await Promise.all([
        api.getEscalations(),
        api.getHandoffQueue(),
      ])
      setEscalations(e)
      setQueue(q)
    } catch {
      setEscalations([])
      setQueue([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [load])

  const items = tab === 'queue' ? queue : escalations

  return (
    <div className="page">
      <PageHeader
        title="Human Handoff Queue"
        subtitle="Escalations and transfer queue for human agents"
        actions={
          <button type="button" className="btn btn-secondary" onClick={load}>
            Refresh
          </button>
        }
      />

      <div className="tabs">
        <button
          type="button"
          className={`tab ${tab === 'queue' ? 'active' : ''}`}
          onClick={() => setTab('queue')}
        >
          Transfer Queue ({queue.length})
        </button>
        <button
          type="button"
          className={`tab ${tab === 'escalations' ? 'active' : ''}`}
          onClick={() => setTab('escalations')}
        >
          All Escalations ({escalations.length})
        </button>
      </div>

      <div className="card">
        {loading ? (
          <p className="loading">Loading…</p>
        ) : items.length === 0 ? (
          <p className="empty">No {tab === 'queue' ? 'queue items' : 'escalations'}</p>
        ) : tab === 'queue' ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Reason</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Category</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((item) => (
                  <tr key={item.id}>
                    <td className="mono">{item.customer_id.slice(-8)}</td>
                    <td>{item.reason || '—'}</td>
                    <td>
                      <span className={`badge badge-priority-${item.priority.toLowerCase()}`}>
                        {item.priority}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge-${statusBadge(item.status)}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>{item.category}</td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Type</th>
                  <th>Reason</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {escalations.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{e.customer_id.slice(-8)}</td>
                    <td>{e.escalation_type}</td>
                    <td>{e.reason}</td>
                    <td>{formatDate(e.created_at)}</td>
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
