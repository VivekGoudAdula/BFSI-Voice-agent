export interface ApiError {
  detail: string | Array<{ msg: string; loc?: string[] }>
}

export interface Customer {
  id: string
  name: string
  phone: string
  created_at: string
  loan_id?: string
  status?: string
  last_call_at?: string | null
  last_call_status?: string
}

export interface Call {
  id: string
  customer_id: string
  phone: string
  status: string
  message: string
  twilio_call_sid: string
  audio_file?: string | null
  agent_id?: string
  agent_name?: string
  created_at: string
}

export interface ActiveCall {
  call_id: string
  call_sid: string
  customer_id: string
  customer_name: string
  agent_id: string
  agent_name: string
  current_state: string
  duration_seconds: number
  started_at?: string | null
}

export interface DashboardSummary {
  total_calls: number
  active_campaigns: number
  completed_calls: number
  escalations: number
  callbacks: number
  agents: number
  customers: number
  live_calls: number
  call_success_rate: number
  recent_activity: RecentActivityItem[]
}

export interface RecentActivityItem {
  id: string
  type: string
  title: string
  description: string
  timestamp: string
}

export interface Campaign {
  id: string
  name: string
  description: string
  agent_id: string
  status: string
  created_at: string
  started_at?: string | null
  ended_at?: string | null
  total_customers: number
}

export interface CampaignAnalytics {
  campaign_id: string
  total_customers: number
  calls_initiated: number
  completed_calls: number
  failed_calls: number
  callbacks: number
  escalations: number
  interested_customers: number
  payment_promises: number
  average_call_duration_seconds: number
  completion_rate: number
}

export interface Agent {
  id: string
  agent_id: string
  name: string
  description: string
  purpose: string
  status: string
  voice_id: string
  language: string
  system_prompt: string
  tools: string[]
  compliance_rules: string[]
  version: number
  created_at?: string
  updated_at?: string
}

export interface Escalation {
  id: string
  call_sid: string
  customer_id: string
  escalation_type: string
  reason: string
  created_at: string
  call_id?: string
}

export interface HandoffQueueItem {
  id: string
  customer_id: string
  call_sid: string
  category: string
  priority: string
  status: string
  created_at: string
  call_id?: string
  reason?: string
}

export interface TranscriptEntry {
  role: string
  content: string
  timestamp: string
}

export interface Transcript {
  call_id: string
  entries: TranscriptEntry[]
}

export interface ConversationAnalytics {
  call_id: string
  agent_id: string
  agent_name: string
  customer_id: string
  duration_seconds?: number
  final_state: string
  escalation_triggered: boolean
  escalation_reason: string
  turn_count: number
  completed: boolean
}

export interface ConversationSummary {
  id: string
  call_id: string
  summary: string
  intent: string
  follow_up_actions: string[]
}

export interface CallOutcome {
  id: string
  call_id: string
  outcome: string
}

export interface ToolLog {
  id: string
  call_id: string
  tool_name: string
  arguments: Record<string, unknown>
  result: unknown
  success: boolean
  execution_time_ms: number
  executed_at: string
}

export interface ComplianceDashboard {
  total_calls: number
  calls_with_consent: number
  calls_without_consent: number
  recorded_calls: number
  escalated_calls: number
  tool_executions: number
  prompt_versions: number
  audit_events: number
}

export interface CompliancePackage {
  call_sid: string
  call_id: string
  disclosure?: { text: string; played_at: string }
  consent?: { status: string; captured_at: string }
  transcript?: { messages: Array<{ role: string; content: string }> }
  tool_executions: ToolLog[]
  events: Array<{ event_type: string; timestamp: string; details: string }>
}

export interface AgentLanguagesResponse {
  agent_id: string
  supported_languages: string[]
  default_language: string
  voice_configs: { language: string; voice_id: string }[]
  prompt_translations: {
    agent_id: string
    language: string
    system_prompt: string
    greeting_template?: string
  }[]
}

export interface LanguageAnalyticsSummary {
  calls_by_language: Record<string, number>
  language_distribution: Record<string, number>
  language_switch_events: number
  language_success_rate: Record<string, number>
  total_calls: number
}

export interface AnalyticsSummary {
  total_conversations: number
  successful_reminders: number
  objections_raised: number
  escalations: number
  average_call_duration_seconds: number
  completion_rate: number
  language_analytics?: LanguageAnalyticsSummary
}

export interface CRMAnalytics {
  total_calls: number
  successful_calls: number
  interested_customers: number
  callback_requests: number
  payment_promises: number
  escalations: number
  average_call_duration_seconds: number
}

export interface HandoffAnalytics {
  total_escalations: number
  escalation_rate: number
  human_transfer_count: number
  human_transfer_rate: number
  queue_waiting: number
  queue_high_priority: number
}

export interface PlatformSettings {
  bank_name: string
  twilio_configured: boolean
  twilio_phone_number: string
  groq_configured: boolean
  groq_model: string
  elevenlabs_configured: boolean
  elevenlabs_voice_id: string
  elevenlabs_model_id: string
  deepgram_configured: boolean
  campaign_batch_size: number
  campaign_call_interval_seconds: number
  campaign_max_concurrent_calls: number
  handoff_enabled: boolean
  human_agent_phone: string
  compliance_enabled: boolean
  compliance_disclosure_template: string
  compliance_consent_prompt: string
  base_url: string
}

export interface Voice {
  voice_id: string
  name: string
  category?: string
}

export interface Tool {
  name: string
  description: string
}

export interface Callback {
  id: string
  customer_id: string
  date: string
  time: string
  status: string
  call_id?: string
}
