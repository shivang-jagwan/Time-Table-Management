import React from 'react'
import { Link } from 'react-router-dom'
import { Toast } from '../components/Toast'
import {
  generateTimetableGlobal,
  listTimeSlots,
  solveTimetableGlobal,
  type SolverConflict,
  type SolveTimetableResponse,
} from '../api/solver'
import { useLayoutContext } from '../components/Layout'

function fmtOrtoolsStatus(code: unknown): string {
  const n = typeof code === 'number' ? code : Number(code)
  if (!Number.isFinite(n)) return String(code)
  const map: Record<number, string> = {
    0: 'UNKNOWN (often timeout)',
    1: 'MODEL_INVALID',
    2: 'FEASIBLE',
    3: 'INFEASIBLE',
    4: 'OPTIMAL',
  }
  return map[n] ? `${n} — ${map[n]}` : String(n)
}

export function GenerateTimetable() {
  const { programCode } = useLayoutContext()
  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [slotCount, setSlotCount] = React.useState<number | null>(null)

  const [seed, setSeed] = React.useState<string>('')
  const [maxTimeSeconds, setMaxTimeSeconds] = React.useState<number>(120)
  const [relaxTeacherLoadLimits, setRelaxTeacherLoadLimits] = React.useState(false)

  const [lastRun, setLastRun] = React.useState<SolveTimetableResponse | null>(null)
  const [lastValidationConflicts, setLastValidationConflicts] = React.useState<SolverConflict[]>([])

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function refresh() {
    setLoading(true)
    try {
      const slots = await listTimeSlots()
      setSlotCount(slots.length)
    } catch (e: any) {
      showToast(`Preflight failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programCode])

  const missingTimeSlots = slotCount === 0
  const canRun = !loading && slotCount != null && !missingTimeSlots

  async function onValidate() {
    setLoading(true)
    setLastValidationConflicts([])
    setLastRun(null)
    try {
      const s = seed.trim() === '' ? null : Number(seed)
      const res = await generateTimetableGlobal({
        program_code: programCode,
        seed: Number.isFinite(s as any) ? s : null,
      })
      if (res.status === 'READY_FOR_SOLVE') {
        showToast('Validation passed. Ready to solve.')
      } else {
        showToast('Validation failed.')
      }
      setLastValidationConflicts(res.conflicts)
    } catch (e: any) {
      showToast(`Validate failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function onSolve() {
    setLoading(true)
    setLastValidationConflicts([])
    setLastRun(null)
    try {
      const s = seed.trim() === '' ? null : Number(seed)
      const res = await solveTimetableGlobal({
        program_code: programCode,
        seed: Number.isFinite(s as any) ? s : null,
        max_time_seconds: Number(maxTimeSeconds),
        relax_teacher_load_limits: Boolean(relaxTeacherLoadLimits),
      })
      setLastRun(res)
      showToast(`Solve status: ${res.status}`)
    } catch (e: any) {
      showToast(`Solve failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <Toast message={toast} />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-lg font-semibold text-slate-900">Generate Timetable</div>
          <div className="mt-1 text-sm text-slate-600">
            Run the solver after completing required setup.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary text-sm font-medium text-slate-800 disabled:opacity-50"
            onClick={refresh}
            disabled={loading}
          >
            {loading ? 'Checking…' : 'Re-check'}
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-3xl border bg-white p-5">
          <div className="text-sm font-semibold text-slate-900">Preflight</div>
          <div className="mt-1 text-xs text-slate-500">
            Quick checks to prevent avoidable solver failures.
          </div>

          <div className="mt-4 space-y-3">
            <div
              className={
                'rounded-2xl border p-4 ' +
                (slotCount == null
                  ? 'bg-slate-50 text-slate-700'
                  : missingTimeSlots
                    ? 'border-amber-200 bg-amber-50'
                    : 'border-emerald-200 bg-emerald-50')
              }
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">Time Slots</div>
                  <div className="mt-1 text-sm text-slate-700">
                    {slotCount == null
                      ? 'Checking…'
                      : missingTimeSlots
                        ? 'No time slots configured.'
                        : `${slotCount} time slots configured.`}
                  </div>
                  {missingTimeSlots ? (
                    <div className="mt-2 text-xs text-slate-600">
                      Generate time slots first to define the day/period grid.
                    </div>
                  ) : null}
                </div>
                {missingTimeSlots ? (
                  <Link
                    to="/time-slots"
                    className="btn-primary shrink-0 text-sm font-semibold"
                  >
                    Configure
                  </Link>
                ) : (
                  <Link
                    to="/time-slots"
                    className="btn-secondary shrink-0 text-sm font-medium text-slate-800"
                  >
                    View
                  </Link>
                )}
              </div>
            </div>

            <div className="rounded-2xl border bg-slate-50 p-4">
              <div className="text-sm font-semibold text-slate-900">Next checks</div>
              <div className="mt-1 text-sm text-slate-600">
                Teachers, subjects, sections, rooms, curriculum, and electives checks will appear here.
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border bg-white p-5">
          <div className="text-sm font-semibold text-slate-900">Solver</div>
          <div className="mt-1 text-xs text-slate-500">
            Program-wide solve. Schedules all active sections across all years and semesters in one model.
          </div>

          <div className="mt-4 grid gap-3">
            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <label className="text-xs font-medium text-slate-600">Program</label>
                <div className="mt-1 rounded-2xl border bg-slate-50 px-3 py-2 text-sm text-slate-800">
                  {programCode}
                </div>
              </div>
              <div className="md:col-span-2">
                <label className="text-xs font-medium text-slate-600">Scope</label>
                <div className="mt-1 rounded-2xl border bg-slate-50 px-3 py-2 text-sm text-slate-800">
                  All active sections (all years + all semesters)
                </div>
                <div className="mt-1 text-[11px] text-slate-500">
                  Prevents cross-year teacher overlaps by construction.
                </div>
              </div>
              <div>
                <label htmlFor="solve_seed" className="text-xs font-medium text-slate-600">Seed (optional)</label>
                <input
                  id="solve_seed"
                  className="input-premium mt-1 w-full text-sm"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder="e.g. 42"
                />
              </div>
            </div>

            <div className="mt-2 text-xs text-slate-500">
              Tip: ensure all required years/semesters have subjects, curriculum, windows, and eligible teachers.
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label htmlFor="solve_max_time" className="text-xs font-medium text-slate-600">Max solve time (seconds)</label>
                <input
                  id="solve_max_time"
                  type="number"
                  min={0.1}
                  step={0.1}
                  className="input-premium mt-1 w-full text-sm"
                  value={maxTimeSeconds}
                  onChange={(e) => setMaxTimeSeconds(Number(e.target.value))}
                />
              </div>
              <div className="flex items-end">
                <label className="checkbox-row w-full rounded-lg border border-white/40 bg-white/70">
                  <input
                    type="checkbox"
                    checked={relaxTeacherLoadLimits}
                    onChange={(e) => setRelaxTeacherLoadLimits(e.target.checked)}
                  />
                  <span className="text-slate-700 font-medium">Relax teacher load limits</span>
                </label>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <button
                className="btn-secondary w-full text-sm font-semibold text-slate-900 disabled:opacity-50"
                disabled={!canRun}
                onClick={onValidate}
              >
                {missingTimeSlots ? 'Configure Time Slots to Continue' : loading ? 'Working…' : 'Validate'}
              </button>
              <button
                className="btn-primary w-full text-sm font-semibold disabled:opacity-50"
                disabled={!canRun}
                onClick={onSolve}
              >
                {missingTimeSlots ? 'Configure Time Slots to Continue' : loading ? 'Solving…' : 'Solve now'}
              </button>
            </div>

            {lastRun ? (
              <div className="rounded-2xl border bg-slate-50 p-4">
                <div className="text-sm font-semibold text-slate-900">Last solve</div>
                <div className="mt-1 text-sm text-slate-700">Status: {lastRun.status}</div>
                <div className="mt-1 text-sm text-slate-700">Entries written: {lastRun.entries_written}</div>
                <div className="mt-1 text-sm text-slate-700">Conflicts: {lastRun.conflicts.length}</div>

                {lastRun.status === 'ERROR' ? (
                  <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-slate-800">
                    Solver returned <span className="font-semibold">ERROR</span> (no timetable entries).
                    Most commonly this is a <span className="font-semibold">timeout</span>.
                    Try increasing <span className="font-semibold">Max solve time</span> (e.g. 30–60s) or enable
                    <span className="font-semibold"> Relax teacher load limits</span>, then solve again.
                  </div>
                ) : null}

                {lastRun.conflicts.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {lastRun.conflicts.slice(0, 12).map((c, idx) => (
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
                    {lastRun.conflicts.length > 12 ? (
                      <div className="text-xs text-slate-500">Showing first 12 conflicts. See Conflicts page for all.</div>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    to={`/conflicts?runId=${encodeURIComponent(lastRun.run_id)}`}
                    className="btn-secondary text-sm font-medium text-slate-800"
                  >
                    View in Conflicts
                  </Link>
                  <Link
                    to={`/timetable?runId=${encodeURIComponent(lastRun.run_id)}`}
                    className="btn-primary text-sm font-semibold"
                  >
                    View Timetable Grid
                  </Link>
                </div>
              </div>
            ) : null}

            {lastValidationConflicts.length > 0 ? (
              <div className="rounded-2xl border bg-amber-50 p-4">
                <div className="text-sm font-semibold text-slate-900">Validation conflicts</div>
                <div className="mt-2 space-y-2">
                  {lastValidationConflicts.slice(0, 20).map((c, idx) => (
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
                        <div className="mt-2 text-xs text-slate-600">
                          {c.metadata.ortools_status != null ? (
                            <div>OR-Tools status: {fmtOrtoolsStatus(c.metadata.ortools_status)}</div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
                {lastValidationConflicts.length > 20 ? (
                  <div className="mt-2 text-xs text-slate-600">Showing first 20.</div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
