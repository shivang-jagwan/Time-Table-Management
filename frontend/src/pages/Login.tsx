import React from 'react'
import { useNavigate } from 'react-router-dom'
import { devLogin, setDemoToken } from '../api/client'
import { Toast } from '../components/Toast'

export function Login() {
  const navigate = useNavigate()
  const [loading, setLoading] = React.useState(false)
  const [toast, setToast] = React.useState('')

  async function onContinue() {
    setLoading(true)
    try {
      await devLogin()
      setDemoToken()
      navigate('/dashboard')
    } catch (e: any) {
      setToast(`Login failed: ${String(e?.message ?? e)}`)
      setTimeout(() => setToast(''), 3500)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-dvh bg-gradient-to-b from-slate-50 via-white to-slate-100">
      <Toast message={toast} />
      <div className="mx-auto flex min-h-dvh max-w-6xl items-center justify-center px-6">
        <div className="w-full max-w-md">
          <div className="rounded-3xl border bg-white/80 p-8 shadow-[0_20px_60px_-25px_rgba(15,23,42,0.35)] backdrop-blur supports-[backdrop-filter]:bg-white/60">
            <div className="text-center">
              <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-900 text-white">
                <svg
                  viewBox="0 0 24 24"
                  className="size-6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M12 3 2 8l10 5 10-5-10-5Z" />
                  <path d="M6 10v6c0 2 2.7 4 6 4s6-2 6-4v-6" />
                </svg>
              </div>
              <h1 className="mt-4 text-xl font-semibold tracking-tight text-slate-900">
                University Timetable System
              </h1>
              <p className="mt-1 text-sm text-slate-600">Computer Science Department</p>
            </div>

            <div className="mt-8">
              <button
                className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:opacity-60"
                onClick={onContinue}
                disabled={loading}
              >
                {loading ? 'Please wait…' : 'Continue with Demo'}
              </button>
              <div className="mt-4 text-center text-xs text-slate-500">
                Demo mode uses a local token only.
              </div>
            </div>
          </div>

          <div className="mt-6 text-center text-xs text-slate-500">
            Secure access and role-based permissions will be enabled in production.
          </div>
        </div>
      </div>
    </div>
  )
}
