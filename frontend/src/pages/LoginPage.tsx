import React from 'react'
import { Link } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import { Toast } from '../components/Toast'
import { useAuth } from '../auth/AuthProvider'

// Default to 127.0.0.1 instead of localhost to avoid IPv6 (::1) resolution issues on Windows
// when the backend is bound to IPv4 only.
// Also normalize env-provided localhost base to 127.0.0.1.
const RAW_API_BASE = import.meta.env.VITE_API_BASE ?? ''

function normalizeApiBase(raw: string): string {
  if (!raw) return ''
  try {
    const u = new URL(raw)
    if (u.hostname === 'localhost') u.hostname = '127.0.0.1'
    return u.toString().replace(/\/$/, '')
  } catch {
    return raw.replace(/\/$/, '').replace(/^http:\/\/localhost(?=:\d+|$)/, 'http://127.0.0.1')
  }
}

const API_BASE = import.meta.env.DEV ? '' : normalizeApiBase(RAW_API_BASE)

export function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [username, setUsername] = React.useState('')
  const [password, setPassword] = React.useState('')

  function showToast(message: string, ms = 3500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (loading) return
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate('/dashboard')
    } catch (e: any) {
      showToast(`Login failed: ${String(e?.message ?? e)}`)
    } finally {
      setLoading(false)
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
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 p-8 shadow-2xl backdrop-blur-xl">
          <div className="flex flex-col items-center text-center">
            <img
              src="/logo.jpg"
              alt="College logo"
              className="h-16 w-16 rounded-full border border-white/20 object-cover"
              onError={(e) => {
                ;(e.currentTarget as HTMLImageElement).style.display = 'none'
              }}
            />
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">Graphic Era Hill University</h1>
            <p className="mt-1 text-sm text-white/70">College Timetable System</p>
          </div>

          <form className="mt-8 space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="block text-xs font-medium text-white/80">Username</label>
              <input
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-white placeholder:text-white/40 outline-none focus:border-white/30"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="Enter username"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-white/80">Password</label>
              <input
                type="password"
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-white placeholder:text-white/40 outline-none focus:border-white/30"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Enter password"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className={
                'group relative flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition ' +
                'hover:scale-[1.01] hover:shadow-indigo-500/40 focus:outline-none focus:ring-2 focus:ring-indigo-300/70 disabled:cursor-not-allowed disabled:opacity-60'
              }
            >
              {loading ? 'Signing in…' : 'Login'}
            </button>

            <div className="pt-2 text-center text-xs text-white/70">
              New here?{' '}
              <Link
                to="/signup"
                className="font-semibold text-white underline decoration-white/40 underline-offset-2"
              >
                Create an account
              </Link>
            </div>

            <div className="pt-3 text-center text-xs text-white/60">© 2026 Computer Science Department</div>
          </form>
        </div>
      </div>
    </div>
  )
}
