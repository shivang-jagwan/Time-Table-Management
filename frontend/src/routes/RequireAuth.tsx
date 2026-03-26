import React from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { state, logout } = useAuth()

  if (state.status === 'loading') {
    return (
      <div className="min-h-dvh grid place-items-center bg-gray-50">
        <div className="text-sm text-gray-600">Loading…</div>
      </div>
    )
  }

  if (state.status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  // Backend protects all non-auth routes with require_admin.
  // If a non-admin user logs in, show a clear message instead of spamming 403s.
  if (String(state.user.role).toUpperCase() !== 'ADMIN') {
    return (
      <div className="min-h-dvh grid place-items-center bg-gray-50 p-6">
        <div className="w-full max-w-md rounded-xl border bg-white p-6 text-sm text-gray-700 shadow-sm">
          <div className="text-base font-semibold text-gray-900">Not authorized</div>
          <p className="mt-2 text-gray-600">
            Your account does not have admin access. Ask an administrator to upgrade your role.
          </p>

          <button
            type="button"
            className="mt-4 inline-flex items-center justify-center rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white"
            onClick={async () => {
              await logout()
              navigate('/login')
            }}
          >
            Logout
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
