// Default to 127.0.0.1 instead of localhost to avoid IPv6 (::1) resolution issues on Windows
// when the backend is bound to IPv4 only.
// Also normalize any env-provided localhost base to 127.0.0.1 (common source of “CORS”/ERR_FAILED in dev).
const RAW_API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

function normalizeApiBase(raw: string): string {
  try {
    const u = new URL(raw)
    if (u.hostname === 'localhost') u.hostname = '127.0.0.1'
    // Strip trailing slash so callers can safely do `${API_BASE}${path}`.
    return u.toString().replace(/\/$/, '')
  } catch {
    return raw.replace(/\/$/, '').replace(/^http:\/\/localhost(?=:\d+|$)/, 'http://127.0.0.1')
  }
}

const API_BASE = normalizeApiBase(RAW_API_BASE)

const DEMO_TOKEN_KEY = 'demo_token'
const ACCESS_TOKEN_KEY = 'access_token'

function getToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setDemoToken(): void {
  localStorage.setItem(DEMO_TOKEN_KEY, 'demo-admin')
}

export function clearDemoToken(): void {
  localStorage.removeItem(DEMO_TOKEN_KEY)
}

export function hasDemoToken(): boolean {
  return Boolean(localStorage.getItem(DEMO_TOKEN_KEY))
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (!res.ok) {
    const contentType = res.headers.get('content-type') ?? ''
    const raw = await res.text()

    // DB outage handling (503): show a stable, user-friendly message.
    if (res.status === 503) {
      // Try to detect the explicit code; otherwise still show the friendly message.
      if (contentType.includes('application/json')) {
        try {
          const data = JSON.parse(raw) as any
          const topCode = typeof data?.code === 'string' ? data.code : null
          const detailCode = typeof data?.detail?.code === 'string' ? data.detail.code : null
          if (topCode === 'DATABASE_UNAVAILABLE' || detailCode === 'DATABASE_UNAVAILABLE') {
            throw new Error('Scheduling system temporarily unavailable. Please retry.')
          }
        } catch {
          // fall through
        }
      }
      throw new Error('Scheduling system temporarily unavailable. Please retry.')
    }

    // FastAPI typically returns JSON errors like: { "detail": ... }
    if (contentType.includes('application/json')) {
      let data: any = null
      try {
        data = JSON.parse(raw)
      } catch {
        data = null
      }

      if (data) {
        const detail = data?.detail

        // New service-level style: { code: string, message: string }
        if (typeof data?.code === 'string') {
          const msg = typeof data?.message === 'string' && data.message.trim() ? data.message : data.code
          throw new Error(msg)
        }

        if (typeof detail === 'string' && detail.trim()) {
          if (detail === 'TIME_SLOTS_IN_USE') {
            throw new Error(
              'Cannot replace time slots while existing timetables exist. Disable “Replace existing” or clear timetable runs/entries first.',
            )
          }
          throw new Error(detail)
        }

        // Our validation style: { detail: { code: string, errors: string[] } }
        if (detail && typeof detail === 'object') {
          const code = typeof detail.code === 'string' ? detail.code : null
          const errors = Array.isArray(detail.errors) ? detail.errors.filter((x: any) => typeof x === 'string') : []
          const msg =
            code && errors.length
              ? `${code}: ${errors.join(', ')}`
              : code
                ? code
                : raw

          throw new Error(msg || `Request failed: ${res.status}`)
        }

        // Pydantic/FastAPI validation: { detail: [{ loc, msg, type }, ...] }
        if (Array.isArray(detail) && detail.length) {
          const msg = detail
            .map((d: any) => (typeof d?.msg === 'string' ? d.msg : null))
            .filter(Boolean)
            .join(', ')
          throw new Error(msg || `Request failed: ${res.status}`)
        }
      }
    }

    throw new Error(raw || `Request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export async function devLogin(): Promise<void> {
  const paths = ['/api/dev/token', '/api/auth/dev-login']
  let lastError: unknown = null

  for (const path of paths) {
    try {
      const data = await apiFetch<{ access_token: string; token_type: string }>(path, { method: 'POST' })
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      return
    } catch (err) {
      lastError = err
    }
  }

  throw lastError
}

export function logout(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(DEMO_TOKEN_KEY)
}

export function isLoggedIn(): boolean {
  // UI auth for Phase 1/2 is demo-token based; keep JWT token support for later.
  return hasDemoToken() || Boolean(getToken())
}
