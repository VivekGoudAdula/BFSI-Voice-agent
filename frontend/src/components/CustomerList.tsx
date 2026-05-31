import { useState } from 'react'
import type { Customer } from '../types'
import { api } from '../api/client'

interface Props {
  customers: Customer[]
  loading: boolean
  onRefresh: () => void
  onCallInitiated: () => void
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}

export function CustomerList({ customers, loading, onRefresh, onCallInitiated }: Props) {
  const [callingId, setCallingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleCall(customerId: string) {
    setError(null)
    setCallingId(customerId)

    try {
      await api.initiateCall(customerId)
      onCallInitiated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate call')
    } finally {
      setCallingId(null)
    }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Customers</h2>
        <button type="button" className="btn btn-call" onClick={onRefresh}>
          Refresh
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <p className="loading">Loading customers…</p>
      ) : customers.length === 0 ? (
        <p className="empty">No customers yet. Add one to get started.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Created</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td className="mono">{c.phone}</td>
                  <td>{formatDate(c.created_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-call"
                      disabled={callingId === c.id}
                      onClick={() => handleCall(c.id)}
                    >
                      {callingId === c.id ? 'Calling…' : 'Call'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
