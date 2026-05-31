import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { Modal } from '../components/common/Modal'
import { PageHeader } from '../components/common/PageHeader'
import { StatCard } from '../components/common/StatCard'
import type { Call, ComplianceDashboard, CompliancePackage } from '../types'
import { formatDate } from '../utils/format'

export function CompliancePage() {
  const [dashboard, setDashboard] = useState<ComplianceDashboard | null>(null)
  const [calls, setCalls] = useState<Call[]>([])
  const [selected, setSelected] = useState<Call | null>(null)
  const [pkg, setPkg] = useState<CompliancePackage | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [d, c] = await Promise.all([
        api.getComplianceDashboard(),
        api.getCalls(),
      ])
      setDashboard(d)
      setCalls(c.slice(0, 50))
    } catch {
      setDashboard(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function viewCall(call: Call) {
    setSelected(call)
    if (!call.twilio_call_sid) {
      setPkg(null)
      return
    }
    try {
      setPkg(await api.getCompliancePackage(call.twilio_call_sid))
    } catch {
      setPkg(null)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Compliance Center"
        subtitle="Consent, disclosure, prompt versions, audit trail, and tool history"
      />

      {loading ? (
        <p className="loading">Loading compliance data…</p>
      ) : dashboard && (
        <div className="stat-grid">
          <StatCard label="Total Calls" value={dashboard.total_calls} />
          <StatCard label="With Consent" value={dashboard.calls_with_consent} accent="#22c55e" />
          <StatCard label="Without Consent" value={dashboard.calls_without_consent} accent="#ef4444" />
          <StatCard label="Recorded" value={dashboard.recorded_calls} />
          <StatCard label="Escalated" value={dashboard.escalated_calls} />
          <StatCard label="Tool Executions" value={dashboard.tool_executions} />
          <StatCard label="Prompt Versions" value={dashboard.prompt_versions} />
          <StatCard label="Audit Events" value={dashboard.audit_events} />
        </div>
      )}

      <div className="card">
        <h2>Call Audit Browser</h2>
        <p className="text-muted">Select a call to view consent, disclosure, transcript, and audit trail.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Phone</th>
                <th>Twilio SID</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((call) => (
                <tr key={call.id}>
                  <td>{formatDate(call.created_at)}</td>
                  <td className="mono">{call.phone}</td>
                  <td className="mono">{call.twilio_call_sid?.slice(-12) || '—'}</td>
                  <td>
                    <button type="button" className="btn btn-sm" onClick={() => viewCall(call)}>
                      View Compliance
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        open={!!selected}
        title={`Compliance — ${selected?.phone ?? ''}`}
        onClose={() => { setSelected(null); setPkg(null) }}
        wide
      >
        {!selected?.twilio_call_sid ? (
          <p className="text-muted">No Twilio SID — compliance data unavailable for this call.</p>
        ) : !pkg ? (
          <p className="text-muted">No compliance package found for this call.</p>
        ) : (
          <div className="call-detail">
            <div className="detail-section">
              <h3>Disclosure</h3>
              {pkg.disclosure ? (
                <>
                  <p>{pkg.disclosure.text}</p>
                  <time>{formatDate(pkg.disclosure.played_at)}</time>
                </>
              ) : (
                <p className="text-muted">No disclosure record</p>
              )}
            </div>
            <div className="detail-section">
              <h3>Consent</h3>
              {pkg.consent ? (
                <span className="badge badge-completed">{pkg.consent.status}</span>
              ) : (
                <p className="text-muted">No consent record</p>
              )}
            </div>
            <div className="detail-section">
              <h3>Audit Trail ({pkg.events.length} events)</h3>
              {pkg.events.length > 0 ? (
                <ul className="activity-list">
                  {pkg.events.map((ev, i) => (
                    <li key={i} className="activity-item">
                      <strong>{ev.event_type}</strong>
                      <span>{ev.details}</span>
                      <time>{formatDate(ev.timestamp)}</time>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted">No audit events</p>
              )}
            </div>
            <div className="detail-section">
              <h3>Tool History ({pkg.tool_executions.length})</h3>
              {pkg.tool_executions.length > 0 ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Tool</th><th>Success</th><th>Time</th></tr>
                    </thead>
                    <tbody>
                      {pkg.tool_executions.map((t, i) => (
                        <tr key={i}>
                          <td className="mono">{t.tool_name}</td>
                          <td>{t.success ? '✓' : '✗'}</td>
                          <td>{formatDate(t.executed_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted">No tool executions</p>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
