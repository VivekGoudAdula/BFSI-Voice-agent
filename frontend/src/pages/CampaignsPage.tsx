import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { Modal } from '../components/common/Modal'
import { PageHeader } from '../components/common/PageHeader'
import type { Agent, Campaign } from '../types'
import { formatDate, statusBadge } from '../utils/format'

export function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'upload' | null>(null)
  const [form, setForm] = useState({ name: '', description: '', agent_id: 'emi_agent' })
  const [uploadCampaignId, setUploadCampaignId] = useState('')
  const [message, setMessage] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [c, a] = await Promise.all([api.getCampaigns(), api.getAgents()])
      setCampaigns(c)
      setAgents(a)
    } catch {
      setCampaigns([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await api.createCampaign(form)
      setModal(null)
      setMessage('Campaign created')
      load()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Create failed')
    }
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file || !uploadCampaignId) return
    try {
      const result = await api.uploadCampaignCsv(uploadCampaignId, file)
      setMessage(`Imported ${result.imported} of ${result.total_rows} rows`)
      setModal(null)
      load()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Upload failed')
    }
  }

  async function runAction(id: string, action: 'start' | 'pause' | 'resume' | 'stop') {
    try {
      if (action === 'start') await api.startCampaign(id)
      else if (action === 'pause') await api.pauseCampaign(id)
      else if (action === 'resume') await api.resumeCampaign(id)
      else await api.stopCampaign(id)
      load()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Action failed')
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Campaigns"
        subtitle="Create and manage outbound calling campaigns"
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setModal('upload')}>
              Upload CSV
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setModal('create')}>
              + Create Campaign
            </button>
          </>
        }
      />

      {message && (
        <div className="alert alert-success" onClick={() => setMessage('')}>
          {message}
        </div>
      )}

      <div className="card">
        {loading ? (
          <p className="loading">Loading campaigns…</p>
        ) : campaigns.length === 0 ? (
          <p className="empty">No campaigns yet. Create one to get started.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Campaign Name</th>
                  <th>Status</th>
                  <th>Total Customers</th>
                  <th>Agent</th>
                  <th>Created Date</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                      {c.description && <div className="text-muted">{c.description}</div>}
                    </td>
                    <td>
                      <span className={`badge badge-${statusBadge(c.status)}`}>{c.status}</span>
                    </td>
                    <td>{c.total_customers}</td>
                    <td className="mono">{c.agent_id}</td>
                    <td>{formatDate(c.created_at)}</td>
                    <td>
                      <div className="actions">
                        {c.status === 'draft' && (
                          <button type="button" className="btn btn-sm btn-primary" onClick={() => runAction(c.id, 'start')}>
                            Start
                          </button>
                        )}
                        {c.status === 'running' && (
                          <button type="button" className="btn btn-sm" onClick={() => runAction(c.id, 'pause')}>
                            Pause
                          </button>
                        )}
                        {c.status === 'paused' && (
                          <button type="button" className="btn btn-sm btn-primary" onClick={() => runAction(c.id, 'resume')}>
                            Resume
                          </button>
                        )}
                        {(c.status === 'running' || c.status === 'paused') && (
                          <button type="button" className="btn btn-sm btn-danger" onClick={() => runAction(c.id, 'stop')}>
                            Stop
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => { setUploadCampaignId(c.id); setModal('upload') }}
                        >
                          CSV
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal open={modal === 'create'} title="Create Campaign" onClose={() => setModal(null)}>
        <form className="form" onSubmit={handleCreate}>
          <div className="field">
            <label>Campaign Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="field">
            <label>Description</label>
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="field">
            <label>Agent</label>
            <select value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })}>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn btn-primary">Create</button>
        </form>
      </Modal>

      <Modal open={modal === 'upload'} title="Upload Campaign CSV" onClose={() => setModal(null)}>
        <form className="form" onSubmit={handleUpload}>
          <p className="text-muted">CSV format: Name, Phone, LoanID</p>
          <div className="field">
            <label>Campaign</label>
            <select value={uploadCampaignId} onChange={(e) => setUploadCampaignId(e.target.value)} required>
              <option value="">Select campaign…</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>CSV File</label>
            <input type="file" accept=".csv" ref={fileRef} required />
          </div>
          <button type="submit" className="btn btn-primary">Upload</button>
        </form>
      </Modal>
    </div>
  )
}
