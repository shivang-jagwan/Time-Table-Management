import React from 'react'
import * as authApi from './authApi'

export type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; user: authApi.MeResponse }

type AuthContextValue = {
  state: AuthState
  refresh: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>({ status: 'loading' })

  const refresh = React.useCallback(async () => {
    try {
      const user = await authApi.me()
      setState({ status: 'authenticated', user })
    } catch {
      setState({ status: 'anonymous' })
    }
  }, [])

  React.useEffect(() => {
    void refresh()
  }, [refresh])

  const login = React.useCallback(async (username: string, password: string) => {
    await authApi.login(username, password)
    await refresh()
  }, [refresh])

  const logout = React.useCallback(async () => {
    try {
      await authApi.logoutServer()
    } finally {
      setState({ status: 'anonymous' })
    }
  }, [])

  return (
    <AuthContext.Provider value={{ state, refresh, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
