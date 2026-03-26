import React from 'react'

type Props = {
  logoSrc?: string
  title?: string
  subtitle?: string
  footerText?: string

  onAdminLogin: () => void | Promise<void>
  onDevLogin: () => void | Promise<void>
  loading?: 'admin' | 'dev' | null
}

function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={['h-5 w-5 animate-spin', className ?? ''].join(' ')}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
      />
    </svg>
  )
}

export function AuthCard({
  logoSrc = '/logo.jpg',
  title = 'College Timetable System',
  subtitle = 'Administrative Scheduling Portal',
  footerText = '© 2026 Computer Science Department',
  onAdminLogin,
  onDevLogin,
  loading = null,
}: Props) {
  const [logoFailed, setLogoFailed] = React.useState(false)
  const disabled = loading !== null

  return (
    <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 p-8 shadow-2xl backdrop-blur-xl">
      <div className="flex flex-col items-center text-center">
        {logoFailed ? (
          <div className="grid h-16 w-16 place-items-center rounded-full bg-white/15 text-sm font-semibold text-white">
            CTS
          </div>
        ) : (
          <img
            src={logoSrc}
            alt="College logo"
            className="h-16 w-16 rounded-full border border-white/20 object-cover"
            onError={() => setLogoFailed(true)}
          />
        )}

        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">{title}</h1>
        <p className="mt-1 text-sm text-white/70">{subtitle}</p>
      </div>

      <div className="mt-8 space-y-4">
        <button
          type="button"
          onClick={onAdminLogin}
          disabled={disabled}
          className={
            'group relative flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition ' +
            'hover:scale-[1.03] hover:shadow-indigo-500/40 focus:outline-none focus:ring-2 focus:ring-indigo-300/70 disabled:cursor-not-allowed disabled:opacity-60'
          }
        >
          <span className="absolute inset-0 rounded-xl opacity-0 transition group-hover:opacity-100 bg-white/10" />
          <span className="relative flex items-center gap-2">
            {loading === 'admin' ? (
              <>
                <Spinner className="text-white" />
                <span>Signing in…</span>
              </>
            ) : (
              <span>Admin Login</span>
            )}
          </span>
        </button>

        <button
          type="button"
          onClick={onDevLogin}
          disabled={disabled}
          className={
            'w-full text-center text-xs font-medium text-white/70 transition ' +
            'hover:text-white hover:underline disabled:cursor-not-allowed disabled:opacity-50'
          }
        >
          {loading === 'dev' ? 'Signing in…' : 'Developer Login'}
        </button>

        <div className="pt-3 text-center text-xs text-white/60">{footerText}</div>
      </div>
    </div>
  )
}
