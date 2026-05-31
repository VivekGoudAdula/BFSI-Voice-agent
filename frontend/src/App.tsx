import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { CallLogs } from './components/CallLogs'
import { CustomerForm } from './components/CustomerForm'
import { CustomerList } from './components/CustomerList'
import type { Call, Customer } from './types'
import './App.css'

type Tab = 'customers' | 'calls'

function App() {
  const [tab, setTab] = useState<Tab>('customers')
  const [customers, setCustomers] = useState<Customer[]>([])
  const [calls, setCalls] = useState<Call[]>([])
  const [loadingCustomers, setLoadingCustomers] = useState(true)
  const [loadingCalls, setLoadingCalls] = useState(true)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)

  const loadCustomers = useCallback(async () => {
    setLoadingCustomers(true)
    try {
      const data = await api.getCustomers()
      setCustomers(data)
    } catch {
      setCustomers([])
    } finally {
      setLoadingCustomers(false)
    }
  }, [])

  const loadCalls = useCallback(async () => {
    setLoadingCalls(true)
    try {
      const data = await api.getCalls()
      setCalls(data)
    } catch {
      setCalls([])
    } finally {
      setLoadingCalls(false)
    }
  }, [])

  useEffect(() => {
    api.healthCheck()
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false))
  }, [])

  useEffect(() => {
    loadCustomers()
    loadCalls()
  }, [loadCustomers, loadCalls])

  function handleCallInitiated() {
    loadCalls()
    setTab('calls')
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="brand">
            <div className="brand-icon">ABC</div>
            <div>
              <h1>Voice Agent Platform</h1>
              <p>ABC Bank — Outbound Call Administration</p>
            </div>
          </div>
          <div className="status-pill">
            <span className={`status-dot ${backendOnline === false ? 'offline' : ''}`} />
            {backendOnline === null
              ? 'Checking backend…'
              : backendOnline
                ? 'Backend online'
                : 'Backend offline'}
          </div>
        </div>
      </header>

      <main className="main">
        <div className="tabs">
          <button
            type="button"
            className={`tab ${tab === 'customers' ? 'active' : ''}`}
            onClick={() => setTab('customers')}
          >
            Customers
          </button>
          <button
            type="button"
            className={`tab ${tab === 'calls' ? 'active' : ''}`}
            onClick={() => setTab('calls')}
          >
            Call Logs
          </button>
        </div>

        {tab === 'customers' ? (
          <div className="grid">
            <CustomerForm onCreated={loadCustomers} />
            <CustomerList
              customers={customers}
              loading={loadingCustomers}
              onRefresh={loadCustomers}
              onCallInitiated={handleCallInitiated}
            />
          </div>
        ) : (
          <CallLogs calls={calls} loading={loadingCalls} onRefresh={loadCalls} />
        )}
      </main>

      <footer className="footer">
        Phase 1 — ElevenLabs TTS + Twilio Voice · AI Voice Agent Platform
      </footer>
    </div>
  )
}

export default App
