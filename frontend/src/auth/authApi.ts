import { apiFetch } from '../api/client'

const ACCESS_TOKEN_KEY = 'access_token'

export function setAccessToken(token: string | null): void {
  try {
    if (typeof window === 'undefined') return
    if (!token) {
      window.localStorage.removeItem(ACCESS_TOKEN_KEY)
      return
    }
    window.localStorage.setItem(ACCESS_TOKEN_KEY, token)
  } catch {
    // ignore
  }
}

export type MeResponse = {
  id: string
  tenant_id?: string | null
  username: string
  role: string
  is_active: boolean
  created_at: string
}

export type LoginResponse = {
  ok: boolean
  access_token: string
  token_type: string
}

export async function login(username: string, password: string): Promise<void> {
  const res = await apiFetch<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })

  if (res?.access_token) setAccessToken(res.access_token)
}

export async function signup(username: string, password: string): Promise<void> {
  await apiFetch('/api/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function me(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/api/auth/me')
}

export async function logoutServer(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' })
}
