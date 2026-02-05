// Default to 127.0.0.1 instead of localhost to avoid IPv6 (::1) resolution issues on Windows
// when the backend is bound to IPv4 only.
// Also normalize any env-provided localhost base to 127.0.0.1 (common source of “CORS”/ERR_FAILED in dev).
const RAW_API_BASE = import.meta.env.VITE_API_BASE ?? ''

function normalizeApiBase(raw: string): string {
  if (!raw) return ''
  try {
    const u = new URL(raw)
    if (u.hostname === 'localhost') u.hostname = '127.0.0.1'
    // Strip trailing slash so callers can safely do `${API_BASE}${path}`.
    return u.toString().replace(/\/$/, '')
  } catch {
    return raw.replace(/\/$/, '').replace(/^http:\/\/localhost(?=:\d+|$)/, 'http://127.0.0.1')
  }
}

// Production should use same-origin (Vercel proxy) to avoid third-party cookie issues.
// Use VITE_API_BASE only in dev/local setups.
const API_BASE = import.meta.env.DEV ? normalizeApiBase(RAW_API_BASE) : ''

function getAccessToken(): string | null {
  try {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem('access_token')
  } catch {
    return null
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAccessToken()

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
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

export async function logout(): Promise<void> {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST' })
  } catch {
    // Best-effort logout; cookie may already be cleared.
  }
}
