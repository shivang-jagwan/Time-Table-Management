import React from 'react'
import { useSearchParams } from 'react-router-dom'
import { Toast } from '../components/Toast'
import { useLayoutContext } from '../components/Layout'
import { PremiumSelect } from '../components/PremiumSelect'
import { getRun, listRunConflicts, listRunEntries, listRuns, type RunDetail, type RunSummary, type SolverConflict, type TimetableEntry } from '../api/solver'

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function fmtOrtoolsStatus(code: unknown): string {
  const n = typeof code === 'number' ? code : Number(code)
  if (!Number.isFinite(n)) return String(code)
  const map: Record<number, string> = {
    0: 'UNKNOWN (often timeout/no solution found yet)',
    1: 'MODEL_INVALID',
    2: 'FEASIBLE',
    3: 'INFEASIBLE',
    4: 'OPTIMAL',
  }
  return map[n] ? `${n} — ${map[n]}` : String(n)
}

export function Conflicts() {
  const { programCode, academicYearNumber } = useLayoutContext()
  const [params, setParams] = useSearchParams()
  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const [runs, setRuns] = React.useState<RunSummary[]>([])
  const [runScopeFilter, setRunScopeFilter] = React.useState<'ALL' | 'PROGRAM_GLOBAL' | 'YEAR_ONLY'>(
    'PROGRAM_GLOBAL',
  )
  const [selectedRunId, setSelectedRunId] = React.useState<string | null>(null)
  const [detail, setDetail] = React.useState<RunDetail | null>(null)
  const [conflicts, setConflicts] = React.useState<SolverConflict[]>([])
  const [entries, setEntries] = React.useState<TimetableEntry[]>([])
  const [tab, setTab] = React.useState<'conflicts' | 'entries'>('conflicts')
  const [sectionFilter, setSectionFilter] = React.useState<string>('')

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  function runTag(r: RunSummary): string {
    const scope = String((r as any).parameters?.scope ?? '')
    if (scope === 'PROGRAM_GLOBAL') return 'GLOBAL'
    const year = (r as any).parameters?.academic_year_number
    if (year != null) return `YEAR ${year}`
    return 'LEGACY'
  }

  const visibleRuns = React.useMemo(() => {
    return runs.filter((r) => {
      const scope = String((r as any).parameters?.scope ?? '')
      if (runScopeFilter === 'ALL') return true
      if (runScopeFilter === 'PROGRAM_GLOBAL') return scope === 'PROGRAM_GLOBAL'
      if (runScopeFilter === 'YEAR_ONLY') {
        const year = (r as any).parameters?.academic_year_number
        return year != null && Number(year) === Number(academicYearNumber)
      }
      return true
    })
  }, [runs, runScopeFilter, academicYearNumber])

  async function refreshRuns() {
    setLoading(true)
    try {
      const data = await listRuns({ program_code: programCode, limit: 50 })
      setRuns(data)
      const requested = params.get('runId')
      if (requested) {
        setSelectedRunId(requested)
      } else if (!selectedRunId && data.length > 0) {
        const preferred =
          data.find((x) => String((x as any).parameters?.scope ?? '') === 'PROGRAM_GLOBAL') ?? data[0]
        setSelectedRunId(preferred.id)
      }
    } catch (e: any) {
      showToast(`Load runs failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function loadRun(runId: string) {
    setLoading(true)
    try {
      const d = await getRun(runId)
      setDetail(d)
      setConflicts([])
      setEntries([])
      setSectionFilter('')
      const c = await listRunConflicts(runId)
      setConflicts(c)
    } catch (e: any) {
      showToast(`Load run failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function loadEntries(runId: string, sectionCode?: string) {
    setLoading(true)
    try {
      const data = await listRunEntries(runId, sectionCode)
      setEntries(data)
    } catch (e: any) {
      showToast(`Load entries failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refreshRuns()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programCode, academicYearNumber])

  React.useEffect(() => {
    if (selectedRunId) loadRun(selectedRunId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId])

  React.useEffect(() => {
    if (!selectedRunId) return
    const p = new URLSearchParams(params)
    p.set('runId', selectedRunId)
    setParams(p, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId])

  const availableSections = React.useMemo(() => {
    const set = new Set<string>()
    for (const e of entries) set.add(e.section_code)
    return Array.from(set).sort()
  }, [entries])

  return (
    <div className="space-y-6">
      <Toast message={toast} />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-lg font-semibold text-slate-900">Conflicts & Runs</div>
          <div className="mt-1 text-sm text-slate-600">
            Browse solver runs for {programCode}. Year selector is used only for filtering.
          </div>
        </div>
        <button
          className="btn-secondary text-sm font-medium text-slate-800 disabled:opacity-50"
          onClick={refreshRuns}
          disabled={loading}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
        <div className="rounded-3xl border bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate-900">Recent runs</div>
            <PremiumSelect
              ariaLabel="Run scope filter"
              className="text-xs"
              value={runScopeFilter}
              onValueChange={(v) => setRunScopeFilter(v as any)}
              options={[
                { value: 'PROGRAM_GLOBAL', label: 'Program Global' },
                { value: 'YEAR_ONLY', label: 'This Year Only' },
                { value: 'ALL', label: 'All' },
              ]}
            />
          </div>
          <div className="mt-3 space-y-2">
            {visibleRuns.length === 0 ? (
              <div className="rounded-2xl border bg-slate-50 p-4 text-sm text-slate-700">No runs found.</div>
            ) : (
              visibleRuns.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelectedRunId(r.id)}
                  className={
                    'w-full rounded-2xl border p-3 text-left ' +
                    (r.id === selectedRunId ? 'border-slate-900 bg-slate-900 text-white' : 'bg-white hover:bg-slate-50')
                  }
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <div className="text-sm font-semibold">{r.status}</div>
                      <div
                        className={
                          'rounded-full px-2 py-0.5 text-[11px] font-semibold ' +
                          (runTag(r).startsWith('GLOBAL')
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-200 text-slate-800')
                        }
                      >
                        {runTag(r)}
                      </div>
                    </div>
                    <div className="text-xs opacity-80">{fmtDate(r.created_at)}</div>
                  </div>
                  <div className="mt-1 text-xs opacity-80">Run: {r.id}</div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="rounded-3xl border bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Run details</div>
              <div className="mt-1 text-xs text-slate-500">{detail ? detail.id : '—'}</div>
            </div>
            <div className="flex items-center gap-2">
              <button
                className={
                  'rounded-2xl px-4 py-2 text-sm font-medium ' +
                  (tab === 'conflicts' ? 'bg-slate-900 text-white' : 'border bg-white text-slate-800')
                }
                onClick={() => setTab('conflicts')}
              >
                Conflicts ({detail?.conflicts_total ?? conflicts.length})
              </button>
              <button
                className={
                  'rounded-2xl px-4 py-2 text-sm font-medium ' +
                  (tab === 'entries' ? 'bg-slate-900 text-white' : 'border bg-white text-slate-800')
                }
                onClick={() => {
                  setTab('entries')
                  if (selectedRunId && entries.length === 0) loadEntries(selectedRunId)
                }}
              >
                Entries ({detail?.entries_total ?? entries.length})
              </button>
            </div>
          </div>

          {tab === 'conflicts' ? (
            <div className="mt-4">
              {conflicts.length === 0 ? (
                <div className="rounded-2xl border bg-slate-50 p-4 text-sm text-slate-700">No conflicts recorded.</div>
              ) : (
                <div className="space-y-2">
                  {conflicts.map((c, idx) => (
                    <div key={idx} className="rounded-2xl border bg-white p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-slate-900">{c.conflict_type}</div>
                        <div
                          className={
                            'rounded-full px-2 py-0.5 text-xs font-semibold ' +
                            (c.severity === 'ERROR'
                              ? 'bg-rose-100 text-rose-700'
                              : c.severity === 'WARN'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-slate-100 text-slate-700')
                          }
                        >
                          {c.severity}
                        </div>
                      </div>
                      <div className="mt-1 text-sm text-slate-700">{c.message}</div>
                      {c.metadata && Object.keys(c.metadata).length > 0 ? (
                        <div className="mt-2 text-xs text-slate-500">
                          {c.metadata.ortools_status != null ? (
                            <div>OR-Tools status: {fmtOrtoolsStatus(c.metadata.ortools_status)}</div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-xs text-slate-500">Tip: filter by section_code to reduce noise.</div>
                <div className="flex items-center gap-2">
                  <input
                    value={sectionFilter}
                    onChange={(e) => setSectionFilter(e.target.value)}
                    placeholder="Section code (optional)"
                    className="input-premium w-52 text-sm"
                  />
                  <button
                    className="btn-secondary text-sm font-medium text-slate-800 disabled:opacity-50"
                    disabled={!selectedRunId}
                    onClick={() => selectedRunId && loadEntries(selectedRunId, sectionFilter.trim() || undefined)}
                  >
                    Load
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Section</th>
                      <th className="px-4 py-3">Subject</th>
                      <th className="px-4 py-3">Teacher</th>
                      <th className="px-4 py-3">Room</th>
                      <th className="px-4 py-3">Slot</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {entries.length === 0 ? (
                      <tr>
                        <td className="px-4 py-4 text-slate-600" colSpan={5}>
                          No entries loaded.
                        </td>
                      </tr>
                    ) : (
                      entries.slice(0, 500).map((e) => (
                        <tr key={e.id} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-medium text-slate-900">{e.section_code}</td>
                          <td className="px-4 py-3 text-slate-700">{e.subject_code}</td>
                          <td className="px-4 py-3 text-slate-700">{e.teacher_code}</td>
                          <td className="px-4 py-3 text-slate-700">{e.room_code}</td>
                          <td className="px-4 py-3 text-slate-700">
                            D{e.day_of_week} #{e.slot_index} ({e.start_time}-{e.end_time})
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {entries.length > 500 ? (
                <div className="text-xs text-slate-500">Showing first 500 entries. Use section filter to narrow.</div>
              ) : null}
              {availableSections.length > 0 ? (
                <div className="text-xs text-slate-500">Loaded sections: {availableSections.join(', ')}</div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
