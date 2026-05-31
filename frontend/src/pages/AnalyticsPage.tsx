import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { BarChart } from '../components/common/BarChart'
import { PageHeader } from '../components/common/PageHeader'
import { StatCard } from '../components/common/StatCard'
import type {
  Agent,
  AnalyticsSummary,
  CRMAnalytics,
  Campaign,
  HandoffAnalytics,
} from '../types'

export function AnalyticsPage() {
  const [agentAnalytics, setAgentAnalytics] = useState<AnalyticsSummary | null>(null)
  const [crmAnalytics, setCrmAnalytics] = useState<CRMAnalytics | null>(null)
  const [handoffAnalytics, setHandoffAnalytics] = useState<HandoffAnalytics | null>(null)
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [aa, crm, handoff, c, ag] = await Promise.all([
        api.getAnalyticsSummary(),
        api.getCRMAnalytics(),
        api.getHandoffAnalytics(),
        api.getCampaigns(),
        api.getAgents(),
      ])
      setAgentAnalytics(aa)
      setCrmAnalytics(crm)
      setHandoffAnalytics(handoff)
      setCampaigns(c)
      setAgents(ag)
    } catch {
      // partial load ok
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) {
    return <div className="page"><p className="loading">Loading analytics…</p></div>
  }

  const callbackRate = crmAnalytics && crmAnalytics.total_calls > 0
    ? Math.round((crmAnalytics.callback_requests / crmAnalytics.total_calls) * 100)
    : 0

  return (
    <div className="page">
      <PageHeader
        title="Analytics"
        subtitle="Call success, callbacks, escalations, campaign and agent performance"
        actions={
          <button type="button" className="btn btn-secondary" onClick={load}>
            Refresh
          </button>
        }
      />

      <div className="stat-grid">
        <StatCard
          label="Call Success Rate"
          value={agentAnalytics ? `${Math.round(agentAnalytics.completion_rate)}%` : '—'}
          accent="#22c55e"
        />
        <StatCard label="Callback Rate" value={`${callbackRate}%`} accent="#f59e0b" />
        <StatCard
          label="Escalation Rate"
          value={handoffAnalytics ? `${Math.round(handoffAnalytics.escalation_rate * 100)}%` : '—'}
          accent="#ef4444"
        />
        <StatCard
          label="Avg Duration"
          value={agentAnalytics ? `${Math.round(agentAnalytics.average_call_duration_seconds)}s` : '—'}
        />
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Agent Performance</h2>
          {agentAnalytics ? (
            <BarChart
              data={[
                { label: 'Conversations', value: agentAnalytics.total_conversations, color: '#3b82f6' },
                { label: 'Successful', value: agentAnalytics.successful_reminders, color: '#22c55e' },
                { label: 'Objections', value: agentAnalytics.objections_raised, color: '#f59e0b' },
                { label: 'Escalations', value: agentAnalytics.escalations, color: '#ef4444' },
              ]}
            />
          ) : (
            <p className="empty">No agent analytics</p>
          )}
          <h3 style={{ marginTop: '1.5rem' }}>Active Agents</h3>
          <BarChart
            data={agents.filter((a) => a.status === 'ACTIVE').map((a) => ({
              label: a.name,
              value: a.tools.length,
              color: '#6366f1',
            }))}
          />
        </div>

        <div className="card">
          <h2>Campaign Performance</h2>
          {campaigns.length > 0 ? (
            <BarChart
              data={campaigns.map((c) => ({
                label: c.name.slice(0, 20),
                value: c.total_customers,
                color: c.status === 'running' ? '#22c55e' : '#3b82f6',
              }))}
            />
          ) : (
            <p className="empty">No campaigns</p>
          )}

          <h3 style={{ marginTop: '1.5rem' }}>CRM Outcomes</h3>
          {crmAnalytics ? (
            <BarChart
              data={[
                { label: 'Interested', value: crmAnalytics.interested_customers, color: '#22c55e' },
                { label: 'Callbacks', value: crmAnalytics.callback_requests, color: '#f59e0b' },
                { label: 'Payment Promised', value: crmAnalytics.payment_promises, color: '#3b82f6' },
                { label: 'Escalated', value: crmAnalytics.escalations, color: '#ef4444' },
              ]}
            />
          ) : (
            <p className="empty">No CRM data</p>
          )}
        </div>
      </div>

      {handoffAnalytics && (
        <div className="card">
          <h2>Handoff & Escalation</h2>
          <div className="stat-grid stat-grid-inline">
            <StatCard label="Total Escalations" value={handoffAnalytics.total_escalations} />
            <StatCard label="Human Transfers" value={handoffAnalytics.human_transfer_count} />
            <StatCard label="Queue Waiting" value={handoffAnalytics.queue_waiting} />
            <StatCard label="High Priority" value={handoffAnalytics.queue_high_priority} accent="#ef4444" />
          </div>
        </div>
      )}
    </div>
  )
}
