import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Toast } from '../components/Toast'
import { AuthCard } from '../components/AuthCard'
import { devLogin, setDemoToken } from '../api/client'

// Default to 127.0.0.1 instead of localhost to avoid IPv6 (::1) resolution issues on Windows
// when the backend is bound to IPv4 only.
// Also normalize env-provided localhost base to 127.0.0.1.
const RAW_API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

function normalizeApiBase(raw: string): string {
  try {
    const u = new URL(raw)
    if (u.hostname === 'localhost') u.hostname = '127.0.0.1'
    return u.toString().replace(/\/$/, '')
  } catch {
    return raw.replace(/\/$/, '').replace(/^http:\/\/localhost(?=:\d+|$)/, 'http://127.0.0.1')
  }
}

const API_BASE = normalizeApiBase(RAW_API_BASE)

export function LoginPage() {
  const navigate = useNavigate()
  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState<'admin' | 'dev' | null>(null)

  function showToast(message: string, ms = 3500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function onAdminLogin() {
    if (loading) return
    setLoading('admin')

    // Give React a tick to paint the loading UI before navigating away.
    window.setTimeout(() => {
      window.location.assign(`${API_BASE}/auth/admin-login`)
    }, 50)
  }

  async function onDevLogin() {
    if (loading) return
    setLoading('dev')

    // Preferred: hit the backend endpoint requested by spec.
    try {
      const res = await fetch(`${API_BASE}/api/auth/dev-login`, { method: 'POST' })
      const contentType = res.headers.get('content-type') ?? ''

      if (!res.ok) {
        throw new Error(`Developer login failed (${res.status})`)
      }

      if (contentType.includes('application/json')) {
        const data = (await res.json()) as any
        if (typeof data?.access_token === 'string' && data.access_token) {
          localStorage.setItem('access_token', data.access_token)
          setDemoToken()
          navigate('/dashboard')
          return
        }
      }

      // If the endpoint uses a redirect/cookie flow, navigate to dashboard and let auth settle.
      navigate('/dashboard')
      return
    } catch {
      // Fallback: preserve existing local/dev workflow.
      try {
        await devLogin()
        setDemoToken()
        navigate('/dashboard')
        return
      } catch (e: any) {
        showToast(`Login failed: ${String(e?.message ?? e)}`)
      }
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="relative min-h-screen">
      <Toast message={toast} />

      {/* Background image */}
      <div className="absolute inset-0 bg-[url('/campus-bg.svg')] bg-cover bg-center" aria-hidden="true" />

      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/60" aria-hidden="true" />

      {/* Content */}
      <div className="relative flex min-h-screen items-center justify-center px-6 py-10">
        <AuthCard onAdminLogin={onAdminLogin} onDevLogin={onDevLogin} loading={loading} />
      </div>
    </div>
  )
}
