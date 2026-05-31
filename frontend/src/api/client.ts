import type { ApiError, Call, Customer } from '../types'

function formatApiError(detail: ApiError['detail']): string {
  if (typeof detail === 'string') return detail
  return detail.map((item) => item.msg).join(', ')
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as ApiError
      if (body.detail) detail = formatApiError(body.detail)
    } catch {
      // ignore parse errors
    }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export const api = {
  getCustomers: () => request<Customer[]>('/customers'),

  createCustomer: (data: { name: string; phone: string }) =>
    request<Customer>('/customers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getCalls: () => request<Call[]>('/calls'),

  initiateCall: (customerId: string) =>
    request<Call>('/calls/initiate', {
      method: 'POST',
      body: JSON.stringify({ customer_id: customerId }),
    }),

  healthCheck: () => request<{ status: string }>('/health'),
}
