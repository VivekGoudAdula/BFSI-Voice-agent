import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Modal } from '../components/common/Modal'
import { PageHeader } from '../components/common/PageHeader'
import type { Agent, Call, Customer } from '../types'
import { formatDate, statusBadge } from '../utils/format'

export function CustomersPage() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [callError, setCallError] = useState('')
  const [callSuccess, setCallSuccess] = useState('')
  const [callingId, setCallingId] = useState<string | null>(null)
  const [modal, setModal] = useState<'add' | 'edit' | 'history' | 'call' | null>(null)
  const [selected, setSelected] = useState<Customer | null>(null)
  const [callAgentId, setCallAgentId] = useState('')
  const [history, setHistory] = useState<Call[]>([])
  const [form, setForm] = useState({ name: '', phone: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setCustomers(await api.getCustomers(search))
    } catch {
      setCustomers([])
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    api.getAgents().then(setAgents).catch(() => setAgents([]))
  }, [])

  useEffect(() => {
    const timer = setTimeout(load, 300)
    return () => clearTimeout(timer)
  }, [load])

  function openAdd() {
    setForm({ name: '', phone: '' })
    setSelected(null)
    setModal('add')
  }

  function openEdit(c: Customer) {
    setForm({ name: c.name, phone: c.phone })
    setSelected(c)
    setModal('edit')
  }

  async function openHistory(c: Customer) {
    setSelected(c)
    setModal('history')
    try {
      setHistory(await api.getCustomerCalls(c.id))
    } catch {
      setHistory([])
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      if (modal === 'edit' && selected) {
        await api.updateCustomer(selected.id, form)
      } else {
        await api.createCustomer(form)
      }
      setModal(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  function openCall(c: Customer) {
    setSelected(c)
    setCallAgentId('')
    setCallError('')
    setModal('call')
  }

  async function handleCall(e: React.FormEvent) {
    e.preventDefault()
    if (!selected) return

    setCallError('')
    setCallSuccess('')
    setCallingId(selected.id)

    try {
      await api.initiateCall(selected.id, callAgentId)
      setModal(null)
      setCallSuccess(`Outbound call started to ${selected.name}`)
      load()
      setTimeout(() => setCallSuccess(''), 5000)
      navigate('/live-calls')
    } catch (err) {
      setCallError(err instanceof Error ? err.message : 'Failed to initiate call')
    } finally {
      setCallingId(null)
    }
  }

  async function handleDelete(c: Customer) {
    if (!confirm(`Delete customer ${c.name}?`)) return
    try {
      await api.deleteCustomer(c.id)
      load()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Customers"
        subtitle="Manage customer records and call history"
        actions={
          <button type="button" className="btn btn-primary" onClick={openAdd}>
            + Add Customer
          </button>
        }
      />

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search by name or phone…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="search-input"
        />
        <button type="button" className="btn btn-secondary" onClick={load}>
          Refresh
        </button>
      </div>

      {callSuccess && <div className="alert alert-success">{callSuccess}</div>}
      {callError && !modal && <div className="alert alert-error">{callError}</div>}

      <div className="card">
        {loading ? (
          <p className="loading">Loading customers…</p>
        ) : customers.length === 0 ? (
          <p className="empty">No customers found</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Loan ID</th>
                  <th>Status</th>
                  <th>Last Call</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {customers.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td className="mono">{c.phone}</td>
                    <td className="mono">{c.loan_id || '—'}</td>
                    <td>
                      <span className={`badge badge-${statusBadge(c.status || 'active')}`}>
                        {c.status || 'active'}
                      </span>
                    </td>
                    <td>{formatDate(c.last_call_at)}</td>
                    <td>
                      <div className="actions">
                        <button
                          type="button"
                          className="btn btn-sm btn-call"
                          disabled={callingId === c.id}
                          onClick={() => openCall(c)}
                        >
                          {callingId === c.id ? 'Calling…' : 'Call'}
                        </button>
                        <button type="button" className="btn btn-sm" onClick={() => openHistory(c)}>
                          History
                        </button>
                        <button type="button" className="btn btn-sm" onClick={() => openEdit(c)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDelete(c)}
                        >
                          Delete
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

      <Modal
        open={modal === 'add' || modal === 'edit'}
        title={modal === 'edit' ? 'Edit Customer' : 'Add Customer'}
        onClose={() => setModal(null)}
      >
        <form className="form" onSubmit={handleSubmit}>
          {error && <div className="alert alert-error">{error}</div>}
          <div className="field">
            <label htmlFor="name">Name</label>
            <input
              id="name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="phone">Phone (E.164)</label>
            <input
              id="phone"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="+919876543210"
              required
            />
          </div>
          <button type="submit" className="btn btn-primary">
            {modal === 'edit' ? 'Save Changes' : 'Create Customer'}
          </button>
        </form>
      </Modal>

      <Modal
        open={modal === 'call'}
        title={`Call ${selected?.name ?? ''}`}
        onClose={() => setModal(null)}
      >
        <form className="form" onSubmit={handleCall}>
          {callError && <div className="alert alert-error">{callError}</div>}
          <p className="text-muted">
            Place an outbound call to <strong>{selected?.phone}</strong>
            {selected?.loan_id ? ` · Loan ${selected.loan_id}` : ''}
          </p>
          <div className="field">
            <label>Agent</label>
            <select
              value={callAgentId}
              onChange={(e) => setCallAgentId(e.target.value)}
            >
              <option value="">Default (EMI Reminder Agent)</option>
              {agents.filter((a) => a.status === 'ACTIVE').map((a) => (
                <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={callingId === selected?.id}
          >
            {callingId === selected?.id ? 'Starting call…' : 'Start Call'}
          </button>
        </form>
      </Modal>

      <Modal
        open={modal === 'history'}
        title={`Call History — ${selected?.name ?? ''}`}
        onClose={() => setModal(null)}
        wide
      >
        {history.length === 0 ? (
          <p className="empty">No calls for this customer</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Agent</th>
                  <th>Phone</th>
                </tr>
              </thead>
              <tbody>
                {history.map((call) => (
                  <tr key={call.id}>
                    <td>{formatDate(call.created_at)}</td>
                    <td>
                      <span className={`badge badge-${statusBadge(call.status)}`}>
                        {call.status}
                      </span>
                    </td>
                    <td>{call.agent_name || '—'}</td>
                    <td className="mono">{call.phone}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  )
}
