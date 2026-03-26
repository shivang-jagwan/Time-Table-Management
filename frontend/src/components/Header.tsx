import React from 'react'
import { listPrograms, type Program } from '../api/programs'
import { useAuth } from '../auth/AuthProvider'
import { PremiumSelect } from './PremiumSelect'

function initialsFromName(name: string) {
  const parts = name
    .split(/\s+/)
    .map((p) => p.trim())
    .filter(Boolean)
  const a = parts[0]?.[0] ?? 'U'
  const b = parts[1]?.[0] ?? parts[0]?.[1] ?? ''
  return (a + b).toUpperCase()
}

export function Header({
  collapsed,
  onToggleSidebar,
  programCode,
  academicYearNumber,
  onChangeProgramCode,
  onChangeAcademicYearNumber,
  onLogout,
}: {
  collapsed: boolean
  onToggleSidebar: () => void
  programCode: string
  academicYearNumber: number
  onChangeProgramCode: (v: string) => void
  onChangeAcademicYearNumber: (v: number) => void
  onLogout: () => void
}) {
  const { state } = useAuth()
  const [programs, setPrograms] = React.useState<Program[]>([])
  const [useCustomProgram, setUseCustomProgram] = React.useState(false)

  const displayName = state.status === 'authenticated' ? state.user.username : 'User'
  const roleLabel =
    state.status === 'authenticated'
      ? state.user.role
      : state.status === 'loading'
        ? 'Loading…'
        : 'Signed out'
  const userInitials = state.status === 'authenticated' ? initialsFromName(state.user.username) : 'U'

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await listPrograms()
        if (cancelled) return
        setPrograms(data)
      } catch {
        // Non-blocking: backend might be down or user not logged in yet.
        if (cancelled) return
        setPrograms([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const hasPrograms = programs.length > 0
  const knownProgramCodes = React.useMemo(() => new Set(programs.map((p) => p.code)), [programs])
  const isKnownProgram = knownProgramCodes.has(programCode)

  React.useEffect(() => {
    if (!hasPrograms) return
    if (!isKnownProgram && programCode.trim() !== '') setUseCustomProgram(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPrograms, isKnownProgram])

  return (
    <header className="sticky top-0 z-30 h-14 border-b border-white/25 bg-[rgba(209,250,229,0.55)] backdrop-blur-[10px]">
      <div className="mx-auto flex h-full max-w-[1400px] items-center justify-between gap-3 px-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="grid size-10 place-items-center rounded-xl border border-white/30 bg-white/55 text-slate-800 hover:bg-white/65 backdrop-blur-[10px]"
            onClick={onToggleSidebar}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-slate-900">University Timetable System</div>
            <div className="text-[11px] text-slate-500">Computer Science Department</div>
          </div>
        </div>

        <div className="hidden flex-1 items-center justify-center gap-2 md:flex">
          <div className="flex items-center gap-2 rounded-2xl border border-white/30 bg-white/55 px-3 py-2 shadow-sm backdrop-blur-[10px]">
            <div className="text-xs font-medium text-slate-600">Program</div>
            {hasPrograms ? (
              <div className="flex items-center gap-2">
                <PremiumSelect
                  ariaLabel="Program"
                  className="w-52 px-2 py-1 text-sm"
                  value={useCustomProgram ? '__custom__' : isKnownProgram ? programCode : '__custom__'}
                  onValueChange={(v) => {
                    if (v === '__custom__') {
                      setUseCustomProgram(true)
                      if (programCode.trim() === '') onChangeProgramCode('')
                      return
                    }
                    setUseCustomProgram(false)
                    onChangeProgramCode(v)
                  }}
                  options={[
                    ...programs.map((p) => ({ value: p.code, label: `${p.code} — ${p.name}` })),
                    { value: '__custom__', label: 'Custom…' },
                  ]}
                />

                {useCustomProgram ? (
                  <input
                    className="w-24 rounded-lg border border-white/30 bg-white/55 px-2 py-1 text-sm"
                    value={programCode}
                    onChange={(e) => onChangeProgramCode(e.target.value)}
                    placeholder="Code"
                    aria-label="Custom program code"
                  />
                ) : null}
              </div>
            ) : (
              <input
                className="w-24 rounded-lg border border-white/30 bg-white/55 px-2 py-1 text-sm"
                value={programCode}
                onChange={(e) => onChangeProgramCode(e.target.value)}
                placeholder="CSE"
                aria-label="Program"
              />
            )}
            <div className="ml-2 text-xs font-medium text-slate-600">Year</div>
            <PremiumSelect
              ariaLabel="Academic year"
              className="w-28 px-2 py-1 text-sm"
              value={String(academicYearNumber)}
              onValueChange={(v) => onChangeAcademicYearNumber(Number(v))}
              options={[
                { value: '1', label: 'Year 1' },
                { value: '2', label: 'Year 2' },
                { value: '3', label: 'Year 3' },
              ]}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-2xl border border-white/30 bg-white/55 px-3 py-2 text-sm text-slate-800 backdrop-blur-[10px] md:flex">
            <span className="grid size-7 place-items-center rounded-xl bg-slate-900 text-white">
              {userInitials}
            </span>
            <div className="leading-tight">
              <div className="text-xs font-semibold text-slate-900">{displayName}</div>
              <div className="text-[11px] text-slate-500">{roleLabel}</div>
            </div>
          </div>
          <button
            className="rounded-xl border border-white/30 bg-white/55 px-4 py-2 text-sm font-medium text-slate-900 hover:bg-white/70 backdrop-blur-[10px]"
            onClick={onLogout}
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  )
}
