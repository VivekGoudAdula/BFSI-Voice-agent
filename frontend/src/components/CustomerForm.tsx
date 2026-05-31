import { useState } from 'react'
import { api } from '../api/client'

interface Props {
  onCreated: () => void
}

export function CustomerForm({ onCreated }: Props) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setLoading(true)

    try {
      const customer = await api.createCustomer({ name, phone })
      setSuccess(`Customer "${customer.name}" created successfully.`)
      setName('')
      setPhone('')
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create customer')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Add Customer</h2>
      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}
      <form className="form" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="name">Full Name</label>
          <input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="John Doe"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="phone">Phone Number</label>
          <input
            id="phone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="9876543210 or +919876543210"
            required
          />
          <small style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
            10-digit mobile or E.164 with country code (+91…)
          </small>
        </div>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Creating…' : 'Create Customer'}
        </button>
      </form>
    </div>
  )
}
