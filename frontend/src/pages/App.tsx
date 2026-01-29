import React from 'react'
import { Accordion } from '../components/Accordion'
import { Toast } from '../components/Toast'
import { devLogin, isLoggedIn, logout } from '../api/client'
import { TeacherManagement } from './TeacherManagement'
import { TimetableViewer } from './TimetableViewer'

export function App() {
  const [toast, setToast] = React.useState('')
  const [loggedIn, setLoggedIn] = React.useState(isLoggedIn())

  async function onLogin() {
    try {
      await devLogin()
      setLoggedIn(true)
      setToast('Logged in as Admin')
      setTimeout(() => setToast(''), 2000)
    } catch (e: any) {
      setToast(`Login failed: ${String(e?.message ?? e)}`)
      setTimeout(() => setToast(''), 3000)
    }
  }

  function onLogout() {
    logout()
    setLoggedIn(false)
    setToast('Logged out')
    setTimeout(() => setToast(''), 1500)
  }

  return (
    <div className="min-h-dvh bg-slate-50">
      <Toast message={toast} />
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <div className="text-lg font-semibold text-slate-900">Timetable Dashboard</div>
            <div className="text-xs text-slate-500">Computer Science Dept • Local</div>
          </div>
          <div className="flex items-center gap-2">
            {!loggedIn ? (
              <button
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white"
                onClick={onLogin}
              >
                Login as Admin
              </button>
            ) : (
              <button
                className="rounded-xl border bg-white px-4 py-2 text-sm font-medium text-slate-800"
                onClick={onLogout}
              >
                Logout
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-6 lg:grid-cols-2">
        <section className="space-y-3">
          <div className="text-sm font-semibold text-slate-900">Teacher Management</div>
          <Accordion title="Manage Teachers" defaultOpen>
            {!loggedIn ? (
              <div className="text-sm text-slate-600">Login to manage teachers.</div>
            ) : (
              <TeacherManagement onToast={setToast} />
            )}
          </Accordion>
        </section>

        <section className="space-y-3">
          <div className="text-sm font-semibold text-slate-900">Timetable Builder</div>
          <Accordion title="View Generated Timetable" defaultOpen>
            {!loggedIn ? (
              <div className="text-sm text-slate-600">Login to view solver runs.</div>
            ) : (
              <TimetableViewer onToast={setToast} />
            )}
          </Accordion>
        </section>
      </main>
    </div>
  )
}
