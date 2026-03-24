import React from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { Header } from './layout/Header'
import { Sidebar } from './Sidebar'
import { getLatestProgram } from '../api/programs'

const STORAGE_KEY = 'selected_program_code'
const YEAR_STORAGE_KEY = 'selected_academic_year_number'

type LayoutContextValue = {
  programCode: string
  academicYearNumber: number
  setProgramCode: (v: string) => void
  setAcademicYearNumber: (v: number) => void
}

const LayoutContext = React.createContext<LayoutContextValue | null>(null)

export function useLayoutContext(): LayoutContextValue {
  const ctx = React.useContext(LayoutContext)
  if (!ctx) throw new Error('useLayoutContext must be used within Layout')
  return ctx
}

export function Layout() {
  const navigate = useNavigate()
  const { logout } = useAuth()
  const [collapsed, setCollapsed] = React.useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = React.useState(false)
  const [programCode, setProgramCodeState] = React.useState<string>(() => {
    try { return localStorage.getItem(STORAGE_KEY) ?? '' } catch { return '' }
  })
  const [academicYearNumber, setAcademicYearNumberState] = React.useState<number>(() => {
    try {
      const raw = localStorage.getItem(YEAR_STORAGE_KEY)
      const parsed = Number(raw)
      if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 4) return parsed
    } catch {}
    return 1
  })

  const setProgramCode = React.useCallback((v: string) => {
    setProgramCodeState(v)
    try { localStorage.setItem(STORAGE_KEY, v) } catch {}
  }, [])

  const setAcademicYearNumber = React.useCallback((v: number) => {
    const next = Number(v)
    const safe = Number.isInteger(next) && next >= 1 && next <= 4 ? next : 1
    setAcademicYearNumberState(safe)
    try { localStorage.setItem(YEAR_STORAGE_KEY, String(safe)) } catch {}
  }, [])

  // On mount: if nothing stored, fetch the latest program
  React.useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY)) return
    } catch {}
    getLatestProgram()
      .then(({ program_code }) => setProgramCode(program_code))
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function onLogout() {
    await logout()
    navigate('/login')
  }

  function toggleSidebar() {
    if (typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches) {
      setCollapsed((v) => !v)
      return
    }
    setMobileSidebarOpen((v) => !v)
  }

  return (
    <LayoutContext.Provider
      value={{ programCode, academicYearNumber, setProgramCode, setAcademicYearNumber }}
    >
      <div className="h-screen w-screen overflow-hidden bg-white">
        <Header
          hamburgerOpen={mobileSidebarOpen}
          toggleSidebar={toggleSidebar}
          programCode={programCode}
          academicYearNumber={academicYearNumber}
          onChangeProgramCode={setProgramCode}
          onChangeAcademicYearNumber={setAcademicYearNumber}
          onLogout={onLogout}
        />

        {mobileSidebarOpen ? (
          <button
            type="button"
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px] md:hidden"
            aria-label="Close sidebar"
            onClick={() => setMobileSidebarOpen(false)}
          />
        ) : null}

        <div className="flex h-full w-full">
          <Sidebar
            collapsed={collapsed}
            mobileOpen={mobileSidebarOpen}
            onCloseMobile={() => setMobileSidebarOpen(false)}
          />

          <main
            className={
              [
                'app-scroll-region mt-16 h-[calc(100vh-4rem)] flex-1 overflow-y-auto bg-gray-50 p-6 transition-all duration-300 ease-in-out',
                // On mobile the sidebar overlays, so no left margin.
                collapsed ? 'ml-0 md:ml-20' : 'ml-0 md:ml-64',
              ].join(' ')
            }
          >
            <div className="rounded-2xl bg-white p-6 shadow-sm">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </LayoutContext.Provider>
  )
}
