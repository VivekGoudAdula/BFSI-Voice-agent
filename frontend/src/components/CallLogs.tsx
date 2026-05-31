import type { Call } from '../types'

interface Props {
  calls: Call[]
  loading: boolean
  onRefresh: () => void
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}

function statusClass(status: string) {
  return `badge badge-${status.replace(/\s+/g, '-')}`
}

export function CallLogs({ calls, loading, onRefresh }: Props) {
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Call Logs</h2>
        <button type="button" className="btn btn-call" onClick={onRefresh}>
          Refresh
        </button>
      </div>

      {loading ? (
        <p className="loading">Loading call logs…</p>
      ) : calls.length === 0 ? (
        <p className="empty">No calls yet. Trigger a call from the Customers tab.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Phone</th>
                <th>Message</th>
                <th>Twilio SID</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((call) => (
                <tr key={call.id}>
                  <td>
                    <span className={statusClass(call.status)}>{call.status}</span>
                  </td>
                  <td className="mono">{call.phone}</td>
                  <td style={{ maxWidth: 280 }}>{call.message}</td>
                  <td className="mono">{call.twilio_call_sid || '—'}</td>
                  <td>{formatDate(call.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
