import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { Modal } from '../components/common/Modal'
import { PageHeader } from '../components/common/PageHeader'
import type {
  Call,
  CallOutcome,
  ConversationAnalytics,
  ConversationSummary,
  ToolLog,
  Transcript,
} from '../types'
import { formatDate, statusBadge } from '../utils/format'

export function CallHistoryPage() {
  const [calls, setCalls] = useState<Call[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Call | null>(null)
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [summary, setSummary] = useState<ConversationSummary | null>(null)
  const [outcome, setOutcome] = useState<CallOutcome | null>(null)
  const [analytics, setAnalytics] = useState<ConversationAnalytics | null>(null)
  const [toolLogs, setToolLogs] = useState<ToolLog[]>([])
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setCalls(await api.getCalls())
    } catch {
      setCalls([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function openDetail(call: Call) {
    setSelected(call)
    setDetailLoading(true)
    setTranscript(null)
    setSummary(null)
    setOutcome(null)
    setAnalytics(null)
    setToolLogs([])

    const results = await Promise.allSettled([
      api.getCallTranscript(call.id),
      api.getCallSummary(call.id),
      api.getCallOutcome(call.id),
      api.getAgentAnalytics(call.id),
      api.getToolLogs(call.id),
    ])

    if (results[0].status === 'fulfilled') setTranscript(results[0].value)
    if (results[1].status === 'fulfilled') setSummary(results[1].value)
    if (results[2].status === 'fulfilled') setOutcome(results[2].value)
    if (results[3].status === 'fulfilled') setAnalytics(results[3].value)
    if (results[4].status === 'fulfilled') setToolLogs(results[4].value)

    setDetailLoading(false)
  }

  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
  const recordingUrl = selected?.audio_file
    ? `${apiBase}/webhooks/twilio/play/${selected.audio_file}`
    : null

  return (
    <div className="page">
      <PageHeader
        title="Call Logs"
        subtitle="Browse call history — transcript, recording, summary, and tool calls"
        actions={
          <button type="button" className="btn btn-secondary" onClick={load}>
            Refresh
          </button>
        }
      />

      <div className="card">
        {loading ? (
          <p className="loading">Loading call logs…</p>
        ) : calls.length === 0 ? (
          <p className="empty">No calls recorded yet</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Phone</th>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id}>
                    <td>{formatDate(call.created_at)}</td>
                    <td className="mono">{call.phone}</td>
                    <td>{call.agent_name || '—'}</td>
                    <td>
                      <span className={`badge badge-${statusBadge(call.status)}`}>
                        {call.status}
                      </span>
                    </td>
                    <td>
                      <button type="button" className="btn btn-sm btn-primary" onClick={() => openDetail(call)}>
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal
        open={!!selected}
        title={`Call Details — ${selected?.phone ?? ''}`}
        onClose={() => setSelected(null)}
        wide
      >
        {detailLoading ? (
          <p className="loading">Loading call details…</p>
        ) : (
          <div className="call-detail">
            <div className="detail-grid">
              <div className="detail-section">
                <h3>Summary</h3>
                {summary ? (
                  <>
                    <p>{summary.summary}</p>
                    <p><strong>Intent:</strong> {summary.intent}</p>
                  </>
                ) : (
                  <p className="text-muted">No summary available</p>
                )}
              </div>
              <div className="detail-section">
                <h3>Outcome</h3>
                {outcome ? (
                  <span className="badge badge-completed">{outcome.outcome}</span>
                ) : (
                  <p className="text-muted">No outcome recorded</p>
                )}
              </div>
              <div className="detail-section">
                <h3>Sentiment / Analytics</h3>
                {analytics ? (
                  <dl className="agent-meta">
                    <div><dt>State</dt><dd>{analytics.final_state}</dd></div>
                    <div><dt>Turns</dt><dd>{analytics.turn_count}</dd></div>
                    <div><dt>Escalation</dt><dd>{analytics.escalation_triggered ? analytics.escalation_reason : 'None'}</dd></div>
                    <div><dt>Duration</dt><dd>{analytics.duration_seconds ? `${Math.round(analytics.duration_seconds)}s` : '—'}</dd></div>
                  </dl>
                ) : (
                  <p className="text-muted">No analytics</p>
                )}
              </div>
            </div>

            {recordingUrl && (
              <div className="detail-section">
                <h3>Recording</h3>
                <audio controls src={recordingUrl} className="audio-player" />
              </div>
            )}

            <div className="detail-section">
              <h3>Transcript</h3>
              {transcript && transcript.entries.length > 0 ? (
                <div className="transcript">
                  {transcript.entries.map((entry, i) => (
                    <div key={i} className={`transcript-line transcript-${entry.role}`}>
                      <strong>{entry.role}</strong>
                      <p>{entry.content}</p>
                      <time>{formatDate(entry.timestamp)}</time>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No transcript available</p>
              )}
            </div>

            <div className="detail-section">
              <h3>Tool Calls</h3>
              {toolLogs.length > 0 ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Tool</th>
                        <th>Success</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {toolLogs.map((log) => (
                        <tr key={log.id}>
                          <td className="mono">{log.tool_name}</td>
                          <td>{log.success ? '✓' : '✗'}</td>
                          <td>{log.execution_time_ms}ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted">No tool calls</p>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
