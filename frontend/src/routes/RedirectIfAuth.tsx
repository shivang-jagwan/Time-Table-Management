import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

export function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  const { state } = useAuth()

  if (state.status === 'authenticated') {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}
