import type {
  ActiveCall,
  Agent,
  AnalyticsSummary,
  Call,
  Callback,
  Campaign,
  CampaignAnalytics,
  ComplianceDashboard,
  CompliancePackage,
  ConversationAnalytics,
  ConversationSummary,
  CallOutcome,
  CRMAnalytics,
  Customer,
  DashboardSummary,
  Escalation,
  HandoffAnalytics,
  HandoffQueueItem,
  PlatformSettings,
  Tool,
  ToolLog,
  Transcript,
  Voice,
} from '../types'

function formatApiError(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item: { msg: string }) => item.msg).join(', ')
  }
  return 'Request failed'
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData
  const response = await fetch(`${API_BASE}${path}`, {
    headers: isFormData
      ? { ...options?.headers }
      : { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body.detail) detail = formatApiError(body.detail)
    } catch {
      // ignore
    }
    throw new Error(detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  healthCheck: () => request<{ status: string }>('/health'),

  // Dashboard
  getDashboard: () => request<DashboardSummary>('/admin/dashboard'),

  // Customers
  getCustomers: (search = '') =>
    request<Customer[]>(`/customers${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  getCustomer: (id: string) => request<Customer>(`/customers/${id}`),
  createCustomer: (data: { name: string; phone: string }) =>
    request<Customer>('/customers', { method: 'POST', body: JSON.stringify(data) }),
  updateCustomer: (id: string, data: { name: string; phone: string }) =>
    request<Customer>(`/customers/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCustomer: (id: string) =>
    request<void>(`/customers/${id}`, { method: 'DELETE' }),
  getCustomerCalls: (id: string) => request<Call[]>(`/customers/${id}/calls`),

  // Calls
  getCalls: () => request<Call[]>('/calls'),
  getCall: (id: string) => request<Call>(`/calls/${id}`),
  getActiveCalls: () => request<ActiveCall[]>('/calls/active'),
  getCallTranscript: (id: string) => request<Transcript>(`/calls/${id}/transcript`),
  initiateCall: (customerId: string, agentId = '') =>
    request<Call>('/calls/initiate', {
      method: 'POST',
      body: JSON.stringify({ customer_id: customerId, agent_id: agentId }),
    }),

  // Campaigns
  getCampaigns: () => request<Campaign[]>('/campaigns'),
  getCampaign: (id: string) => request<Campaign>(`/campaigns/${id}`),
  createCampaign: (data: { name: string; description?: string; agent_id?: string }) =>
    request<Campaign>('/campaigns/create', { method: 'POST', body: JSON.stringify(data) }),
  uploadCampaignCsv: (campaignId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('campaign_id', campaignId)
    return request<{ imported: number; failed: number; total_rows: number }>(
      '/campaigns/upload',
      { method: 'POST', body: form },
    )
  },
  startCampaign: (id: string) =>
    request<{ message: string }>(`/campaigns/${id}/start`, { method: 'POST' }),
  pauseCampaign: (id: string) =>
    request<Campaign>(`/campaigns/${id}/pause`, { method: 'POST' }),
  resumeCampaign: (id: string) =>
    request<Campaign>(`/campaigns/${id}/resume`, { method: 'POST' }),
  stopCampaign: (id: string) =>
    request<Campaign>(`/campaigns/${id}/stop`, { method: 'POST' }),
  getCampaignAnalytics: (id: string) =>
    request<CampaignAnalytics>(`/campaigns/${id}/analytics`),

  // Agents
  getAgents: () => request<Agent[]>('/agents'),
  getAgent: (id: string) => request<Agent>(`/agents/${id}`),
  createAgent: (data: Record<string, unknown>) =>
    request<Agent>('/agents', { method: 'POST', body: JSON.stringify(data) }),
  updateAgent: (id: string, data: Record<string, unknown>) =>
    request<Agent>(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAgent: (id: string) =>
    request<void>(`/agents/${id}`, { method: 'DELETE' }),
  activateAgent: (id: string) =>
    request<Agent>(`/agents/${id}/activate`, { method: 'POST' }),
  getAgentLanguages: () => request<Record<string, string>>('/agents/languages'),
  getAgentAnalytics: (callId: string) =>
    request<ConversationAnalytics>(`/agents/analytics/call/${callId}`),
  getAnalyticsSummary: () => request<AnalyticsSummary>('/agents/analytics/summary'),
  getLanguageAnalytics: (agentId?: string) =>
    request<import('../types').LanguageAnalyticsSummary>(
      `/agents/analytics/languages${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''}`,
    ),
  getAgentLanguages: (agentId: string) =>
    request<import('../types').AgentLanguagesResponse>(`/agents/${agentId}/languages`),
  configureAgentLanguages: (agentId: string, body: unknown) =>
    request<import('../types').AgentLanguagesResponse>(`/agents/${agentId}/languages`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Escalations
  getEscalations: () => request<Escalation[]>('/escalations'),
  getHandoffQueue: () => request<HandoffQueueItem[]>('/handoff-queue'),
  getHandoffAnalytics: () => request<HandoffAnalytics>('/escalations/analytics/summary'),

  // CRM
  getCallSummary: (callId: string) =>
    request<ConversationSummary>(`/crm/summary/${callId}`),
  getCallOutcome: (callId: string) =>
    request<CallOutcome>(`/crm/outcome/${callId}`),
  getCRMAnalytics: () => request<CRMAnalytics>('/crm/analytics/summary'),

  // Compliance
  getComplianceDashboard: () =>
    request<ComplianceDashboard>('/compliance/dashboard/summary'),
  getCompliancePackage: (callSid: string) =>
    request<CompliancePackage>(`/compliance/call/${callSid}`),
  getComplianceAudit: (callSid: string) =>
    request<Array<{ event_type: string; timestamp: string; details: string }>>(
      `/compliance/audit/${callSid}`,
    ),

  // Tools
  getTools: () => request<Tool[]>('/tools'),
  getToolLogs: (callId: string) =>
    request<ToolLog[]>(`/tools/logs/call/${callId}`),
  getCallbacks: () => request<Callback[]>('/tools/callbacks'),

  // ElevenLabs
  getVoices: () => request<Voice[]>('/elevenlabs/voices'),

  // Settings
  getSettings: () => request<PlatformSettings>('/admin/settings'),
  updateSettings: (data: Partial<PlatformSettings>) =>
    request<PlatformSettings>('/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
}
