import React from 'react'
import { LoginPage } from './LoginPage'

// Legacy route/component kept for compatibility.
// Production login is implemented in LoginPage.
export function Login() {
  return <LoginPage />
}
