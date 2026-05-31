import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { Modal } from '../components/common/Modal'
import { PageHeader } from '../components/common/PageHeader'
import type { Agent, Voice } from '../types'

const AGENT_TYPES = [
  { id: 'emi_agent', label: 'EMI Agent' },
  { id: 'collections_agent', label: 'Collections Agent' },
  { id: 'loan_agent', label: 'Loan Agent' },
  { id: 'insurance_agent', label: 'Insurance Agent' },
  { id: 'support_agent', label: 'Support Agent' },
]

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [tools, setTools] = useState<Array<{ name: string; description: string }>>([])
  const [voices, setVoices] = useState<Voice[]>([])
  const [languages, setLanguages] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [selected, setSelected] = useState<Agent | null>(null)
  const [form, setForm] = useState({
    agent_id: '',
    name: '',
    description: '',
    purpose: '',
    language: 'en',
    voice_id: '',
    system_prompt: '',
    tools: [] as string[],
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [a, t, v, l] = await Promise.all([
        api.getAgents(),
        api.getTools(),
        api.getVoices().catch(() => []),
        api.getAgentLanguages(),
      ])
      setAgents(a)
      setTools(t)
      setVoices(v)
      setLanguages(l)
    } catch {
      setAgents([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openCreate() {
    setForm({
      agent_id: '',
      name: '',
      description: '',
      purpose: '',
      language: 'en',
      voice_id: '',
      system_prompt: 'You are a helpful banking assistant for ABC Bank.',
      tools: [],
    })
    setSelected(null)
    setModal('create')
  }

  function openEdit(agent: Agent) {
    setForm({
      agent_id: agent.agent_id,
      name: agent.name,
      description: agent.description,
      purpose: agent.purpose,
      language: agent.language,
      voice_id: agent.voice_id,
      system_prompt: agent.system_prompt,
      tools: [...agent.tools],
    })
    setSelected(agent)
    setModal('edit')
  }

  function toggleTool(toolName: string) {
    setForm((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter((t) => t !== toolName)
        : [...prev.tools, toolName],
    }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    try {
      if (modal === 'edit' && selected) {
        await api.updateAgent(selected.agent_id, {
          name: form.name,
          description: form.description,
          purpose: form.purpose,
          language: form.language,
          voice_id: form.voice_id,
          system_prompt: form.system_prompt,
          tools: form.tools,
          status: 'ACTIVE',
        })
      } else {
        await api.createAgent({
          agent_id: form.agent_id,
          name: form.name,
          description: form.description,
          purpose: form.purpose,
          language: form.language,
          voice_id: form.voice_id,
          system_prompt: form.system_prompt,
          tools: form.tools,
        })
      }
      setModal(null)
      load()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Save failed')
    }
  }

  const grouped = AGENT_TYPES.map((type) => ({
    ...type,
    agent: agents.find((a) => a.agent_id === type.id),
  }))

  return (
    <div className="page">
      <PageHeader
        title="Agents"
        subtitle="Configure AI voice agents — prompts, voices, languages, and tools"
        actions={
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            + Create Agent
          </button>
        }
      />

      {loading ? (
        <p className="loading">Loading agents…</p>
      ) : (
        <div className="agent-grid">
          {grouped.map(({ id, label, agent }) => (
            <div key={id} className="card agent-card">
              <div className="agent-card-header">
                <h2>{label}</h2>
                {agent && (
                  <span className={`badge badge-${agent.status.toLowerCase()}`}>
                    {agent.status}
                  </span>
                )}
              </div>
              {agent ? (
                <>
                  <p className="agent-purpose">{agent.purpose || agent.description}</p>
                  <dl className="agent-meta">
                    <div><dt>Voice</dt><dd className="mono">{agent.voice_id || 'default'}</dd></div>
                    <div><dt>Language</dt><dd>{languages[agent.language] || agent.language}</dd></div>
                    <div><dt>Tools</dt><dd>{agent.tools.length} enabled</dd></div>
                    <div><dt>Version</dt><dd>v{agent.version}</dd></div>
                  </dl>
                  <button type="button" className="btn btn-sm btn-primary" onClick={() => openEdit(agent)}>
                    Edit Prompt & Settings
                  </button>
                </>
              ) : (
                <p className="text-muted">Not configured — will use seed on startup</p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h2>All Agents</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Language</th>
                <th>Tools</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id}>
                  <td className="mono">{a.agent_id}</td>
                  <td>{a.name}</td>
                  <td>{languages[a.language] || a.language}</td>
                  <td>{a.tools.join(', ') || '—'}</td>
                  <td>
                    <span className={`badge badge-${a.status.toLowerCase()}`}>{a.status}</span>
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm" onClick={() => openEdit(a)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        open={modal === 'create' || modal === 'edit'}
        title={modal === 'edit' ? `Edit — ${selected?.name}` : 'Create Agent'}
        onClose={() => setModal(null)}
        wide
      >
        <form className="form" onSubmit={handleSubmit}>
          {modal === 'create' && (
            <div className="field">
              <label>Agent ID (slug)</label>
              <input
                value={form.agent_id}
                onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
                pattern="[a-z][a-z0-9_]*"
                placeholder="my_agent"
                required
              />
            </div>
          )}
          <div className="field">
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="field">
            <label>Purpose</label>
            <input value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
          </div>
          <div className="field-row">
            <div className="field">
              <label>Language</label>
              <select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
                {Object.entries(languages).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Voice</label>
              <select value={form.voice_id} onChange={(e) => setForm({ ...form, voice_id: e.target.value })}>
                <option value="">Default voice</option>
                {voices.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>{v.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="field">
            <label>System Prompt</label>
            <textarea
              rows={8}
              value={form.system_prompt}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
              required
            />
          </div>
          <div className="field">
            <label>Enable Tools</label>
            <div className="tool-checkboxes">
              {tools.map((t) => (
                <label key={t.name} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.tools.includes(t.name)}
                    onChange={() => toggleTool(t.name)}
                  />
                  <span>{t.name}</span>
                  <small>{t.description}</small>
                </label>
              ))}
            </div>
          </div>
          <button type="submit" className="btn btn-primary">
            {modal === 'edit' ? 'Save Changes' : 'Create Agent'}
          </button>
        </form>
      </Modal>
    </div>
  )
}
