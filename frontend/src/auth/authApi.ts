import { apiFetch } from '../api/client'

export type MeResponse = {
  id: string
  username: string
  role: string
  is_active: boolean
  created_at: string
}

export async function login(username: string, password: string): Promise<void> {
  await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
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
