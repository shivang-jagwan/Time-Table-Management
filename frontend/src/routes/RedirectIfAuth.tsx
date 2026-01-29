import React from 'react'
import { Navigate } from 'react-router-dom'
import { isLoggedIn } from '../api/client'

export function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  if (isLoggedIn()) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}
