export interface Customer {
  id: string
  name: string
  phone: string
  created_at: string
}

export interface Call {
  id: string
  customer_id: string
  phone: string
  status: string
  message: string
  twilio_call_sid: string
  audio_file?: string | null
  created_at: string
}

export interface ApiError {
  detail: string | Array<{ msg: string; loc?: string[] }>
}
