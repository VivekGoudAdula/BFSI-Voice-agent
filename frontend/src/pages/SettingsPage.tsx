import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { PageHeader } from '../components/common/PageHeader'
import type { PlatformSettings, Voice } from '../types'

export function SettingsPage() {
  const [settings, setSettings] = useState<PlatformSettings | null>(null)
  const [voices, setVoices] = useState<Voice[]>([])
  const [languages, setLanguages] = useState<Record<string, string>>({})
  const [form, setForm] = useState<Partial<PlatformSettings>>({})
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, v, l] = await Promise.all([
        api.getSettings(),
        api.getVoices().catch(() => []),
        api.getAgentLanguages(),
      ])
      setSettings(s)
      setForm(s)
      setVoices(v)
      setLanguages(l)
    } catch {
      setSettings(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    try {
      const updated = await api.updateSettings(form)
      setSettings(updated)
      setForm(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Save failed')
    }
  }

  if (loading) {
    return <div className="page"><p className="loading">Loading settings…</p></div>
  }

  return (
    <div className="page">
      <PageHeader
        title="Settings"
        subtitle="Manage Twilio, Groq, ElevenLabs, voices, and languages"
      />

      {saved && <div className="alert alert-success">Settings saved</div>}

      <form className="settings-form" onSubmit={handleSave}>
        <div className="card">
          <h2>Integrations</h2>
          <div className="settings-grid">
            <div className="setting-row">
              <span>Twilio</span>
              <span className={`badge ${settings?.twilio_configured ? 'badge-completed' : 'badge-failed'}`}>
                {settings?.twilio_configured ? 'Configured' : 'Not configured'}
              </span>
              <span className="mono">{settings?.twilio_phone_number || '—'}</span>
            </div>
            <div className="setting-row">
              <span>Groq</span>
              <span className={`badge ${settings?.groq_configured ? 'badge-completed' : 'badge-failed'}`}>
                {settings?.groq_configured ? 'Configured' : 'Not configured'}
              </span>
              <div className="field" style={{ margin: 0 }}>
                <select
                  value={form.groq_model || ''}
                  onChange={(e) => setForm({ ...form, groq_model: e.target.value })}
                >
                  <option value="llama-3.3-70b-versatile">llama-3.3-70b-versatile</option>
                  <option value="llama-3.1-8b-instant">llama-3.1-8b-instant</option>
                </select>
              </div>
            </div>
            <div className="setting-row">
              <span>ElevenLabs</span>
              <span className={`badge ${settings?.elevenlabs_configured ? 'badge-completed' : 'badge-failed'}`}>
                {settings?.elevenlabs_configured ? 'Configured' : 'Not configured'}
              </span>
              <div className="field" style={{ margin: 0 }}>
                <select
                  value={form.elevenlabs_voice_id || ''}
                  onChange={(e) => setForm({ ...form, elevenlabs_voice_id: e.target.value })}
                >
                  <option value="">Default ({settings?.elevenlabs_voice_id || 'env'})</option>
                  {voices.map((v) => (
                    <option key={v.voice_id} value={v.voice_id}>{v.name}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="setting-row">
              <span>Deepgram STT</span>
              <span className={`badge ${settings?.deepgram_configured ? 'badge-completed' : 'badge-failed'}`}>
                {settings?.deepgram_configured ? 'Configured' : 'Not configured'}
              </span>
            </div>
          </div>
          <p className="text-muted">API keys are configured via backend <code>.env</code> — not editable here.</p>
        </div>

        <div className="card">
          <h2>Platform</h2>
          <div className="field">
            <label>Bank Name</label>
            <input
              value={form.bank_name || ''}
              onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Base URL</label>
            <input value={settings?.base_url || ''} disabled />
          </div>
        </div>

        <div className="card">
          <h2>Languages</h2>
          <div className="language-grid">
            {Object.entries(languages).map(([code, label]) => (
              <span key={code} className="language-chip">{label} ({code})</span>
            ))}
          </div>
        </div>

        <div className="card">
          <h2>Campaign Engine</h2>
          <div className="field-row">
            <div className="field">
              <label>Batch Size</label>
              <input
                type="number"
                min={1}
                max={100}
                value={form.campaign_batch_size ?? 10}
                onChange={(e) => setForm({ ...form, campaign_batch_size: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Call Interval (s)</label>
              <input
                type="number"
                min={0.5}
                step={0.5}
                value={form.campaign_call_interval_seconds ?? 5}
                onChange={(e) => setForm({ ...form, campaign_call_interval_seconds: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Max Concurrent</label>
              <input
                type="number"
                min={1}
                max={200}
                value={form.campaign_max_concurrent_calls ?? 50}
                onChange={(e) => setForm({ ...form, campaign_max_concurrent_calls: Number(e.target.value) })}
              />
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Compliance & Handoff</h2>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.compliance_enabled ?? true}
              onChange={(e) => setForm({ ...form, compliance_enabled: e.target.checked })}
            />
            Compliance enabled
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.handoff_enabled ?? true}
              onChange={(e) => setForm({ ...form, handoff_enabled: e.target.checked })}
            />
            Human handoff enabled
          </label>
          <div className="field">
            <label>Human Agent Phone</label>
            <input
              value={form.human_agent_phone || ''}
              onChange={(e) => setForm({ ...form, human_agent_phone: e.target.value })}
              placeholder="+919876543210"
            />
          </div>
          <div className="field">
            <label>AI Disclosure Template</label>
            <textarea
              rows={3}
              value={form.compliance_disclosure_template || ''}
              onChange={(e) => setForm({ ...form, compliance_disclosure_template: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Consent Prompt</label>
            <textarea
              rows={2}
              value={form.compliance_consent_prompt || ''}
              onChange={(e) => setForm({ ...form, compliance_consent_prompt: e.target.value })}
            />
          </div>
        </div>

        <button type="submit" className="btn btn-primary">Save Settings</button>
      </form>
    </div>
  )
}
