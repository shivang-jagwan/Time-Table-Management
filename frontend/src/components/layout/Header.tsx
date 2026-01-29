import React from 'react'
import { listPrograms, type Program } from '../../api/programs'
import { HamburgerButton } from './HamburgerButton'
import { PremiumSelect } from '../PremiumSelect'

type Props = {
  hamburgerOpen: boolean
  toggleSidebar: () => void

  programCode: string
  academicYearNumber: number
  onChangeProgramCode: (v: string) => void
  onChangeAcademicYearNumber: (v: number) => void

  onLogout: () => void
}

function initialsFromName(name: string) {
  const parts = name
    .split(/\s+/)
    .map((p) => p.trim())
    .filter(Boolean)
  const a = parts[0]?.[0] ?? 'A'
  const b = parts[1]?.[0] ?? parts[0]?.[1] ?? 'D'
  return (a + b).toUpperCase()
}

export function Header({
  hamburgerOpen,
  toggleSidebar,
  programCode,
  academicYearNumber,
  onChangeProgramCode,
  onChangeAcademicYearNumber,
  onLogout,
}: Props) {
  const [programs, setPrograms] = React.useState<Program[]>([])
  const [useCustomProgram, setUseCustomProgram] = React.useState(false)

  const [logoFailed, setLogoFailed] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await listPrograms()
        if (cancelled) return
        setPrograms(data)
      } catch {
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

  const controlSelect =
    'rounded-lg border border-white/30 bg-white/15 px-3 py-2 text-sm text-white shadow-sm backdrop-blur-sm transition ' +
    'hover:border-white/50 focus:outline-none focus:ring-2 focus:ring-white/40'

  const controlInput =
    'rounded-lg border border-white/30 bg-white/15 px-3 py-2 text-sm text-white shadow-sm backdrop-blur-sm transition ' +
    'placeholder:text-white/70 hover:border-white/50 focus:outline-none focus:ring-2 focus:ring-white/40'

  const displayName = 'Demo Admin'
  const userInitials = initialsFromName(displayName)

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-16 bg-gradient-to-r from-green-600 to-green-500 shadow-md backdrop-blur-sm border-b border-green-400/30 text-white">
      <div className="flex h-full w-full items-center justify-between px-6">
        {/* Left */}
        <div className="flex items-center gap-3">
          <HamburgerButton
            open={hamburgerOpen}
            onClick={toggleSidebar}
            label="Toggle Sidebar"
            className="text-white hover:bg-white/10 focus:ring-white/40"
          />

          <div className="hidden items-center gap-3 md:flex">
            {logoFailed ? (
              <div className="grid h-10 w-10 place-items-center rounded-full bg-white/15 text-xs font-bold text-white shadow-sm ring-1 ring-white/20">
                U
              </div>
            ) : (
              <img
                src="/logo.jpg"
                alt="College logo"
                className="h-10 w-10 rounded-full object-cover shadow-sm ring-1 ring-white/20"
                onError={() => setLogoFailed(true)}
              />
            )}

            <div className="leading-tight">
              <div className="text-[15px] font-semibold text-white">Graphic era hill university</div>
              <div className="text-xs text-white/80">Computer Science Department</div>
            </div>
          </div>
        </div>

        {/* Center (desktop selectors) */}
        <div className="hidden flex-1 items-center justify-center gap-3 md:flex">
          <div className="flex items-center gap-3">
            {hasPrograms ? (
              <div className="flex items-center gap-2">
                <PremiumSelect
                  ariaLabel="Program"
                  className={[controlSelect, 'min-w-[260px]'].join(' ')}
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
                    className={[controlInput, 'w-28'].join(' ')}
                    value={programCode}
                    onChange={(e) => onChangeProgramCode(e.target.value)}
                    placeholder="Code"
                    aria-label="Custom program code"
                  />
                ) : null}
              </div>
            ) : (
              <input
                className={[controlInput, 'w-28'].join(' ')}
                value={programCode}
                onChange={(e) => onChangeProgramCode(e.target.value)}
                placeholder="CSE"
                aria-label="Program"
              />
            )}

            <PremiumSelect
              ariaLabel="Academic year"
              className={[controlSelect, 'w-32'].join(' ')}
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

        {/* Right */}
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-3 md:flex">
            <div className="flex items-center gap-2">
              <span className="grid h-10 w-10 place-items-center rounded-full bg-white/15 text-sm font-semibold text-white ring-1 ring-white/20 transition hover:ring-white/30">
                {userInitials}
              </span>
              <div className="leading-tight">
                <div className="text-sm font-semibold text-white">{displayName}</div>
                <div className="text-xs text-white/80">Local Session</div>
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onLogout}
            className="hidden sm:inline-flex items-center justify-center rounded-lg bg-white/15 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white/40"
          >
            Logout
          </button>

          <button
            type="button"
            onClick={onLogout}
            aria-label="Logout"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-white/15 text-white shadow-sm transition hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white/40 sm:hidden"
          >
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10 17l5-5-5-5" />
              <path d="M15 12H3" />
              <path d="M21 3v18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile centered branding */}
      <div className="pointer-events-none absolute left-1/2 top-0 flex h-16 -translate-x-1/2 items-center md:hidden">
        <div className="flex items-center gap-3">
          {logoFailed ? (
            <div className="grid h-10 w-10 place-items-center rounded-full bg-white/15 text-xs font-bold text-white shadow-sm ring-1 ring-white/20">
              U
            </div>
          ) : (
            <img
              src="/logo.jpg"
              alt="College logo"
              className="h-10 w-10 rounded-full object-cover shadow-sm ring-1 ring-white/20"
              onError={() => setLogoFailed(true)}
            />
          )}
          <div className="leading-tight hidden sm:block">
            <div className="text-[14px] font-semibold text-white">Graphic era hill university</div>
            <div className="text-xs text-white/80">Computer Science Department</div>
          </div>
        </div>
      </div>
    </header>
  )
}
