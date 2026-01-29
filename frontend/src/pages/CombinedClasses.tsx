import React from 'react'
import { Toast } from '../components/Toast'
import { useLayoutContext } from '../components/Layout'
import { PremiumSelect } from '../components/PremiumSelect'
import {
  createCombinedSubjectGroup,
  deleteCombinedSubjectGroup,
  listCombinedSubjectGroups,
  type CombinedSubjectGroupOut,
} from '../api/admin'
import { listSections, type Section } from '../api/sections'
import { listRunEntries, listRuns, type RunSummary, type TimetableEntry } from '../api/solver'
import { listSubjects, type Subject } from '../api/subjects'

type CombinedGroup = {
  id: string
  entries: TimetableEntry[]
}

export function CombinedClasses() {
  const { programCode, academicYearNumber } = useLayoutContext()
  const [tab, setTab] = React.useState<'rules' | 'analyze'>('rules')
  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  // Strict combined subject group rules UI
  const [year, setYear] = React.useState<number>(academicYearNumber)
  const [subjects, setSubjects] = React.useState<Subject[]>([])
  const [sections, setSections] = React.useState<Section[]>([])
  const [groups, setGroups] = React.useState<CombinedSubjectGroupOut[]>([])
  const [subjectCode, setSubjectCode] = React.useState<string>('')
  const [selectedSectionCodes, setSelectedSectionCodes] = React.useState<Set<string>>(new Set())

  const [runs, setRuns] = React.useState<RunSummary[]>([])
  const [runId, setRunId] = React.useState<string>('')
  // Analyzer (existing) UI
  const [analyzedGroups, setAnalyzedGroups] = React.useState<CombinedGroup[]>([])

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  const theorySubjects = React.useMemo(
    () =>
      subjects
        .filter((s) => String(s.subject_type).toUpperCase() === 'THEORY' && s.is_active)
        .sort((a, b) => a.code.localeCompare(b.code)),
    [subjects],
  )

  const activeSections = React.useMemo(
    () => sections.filter((s) => s.is_active).sort((a, b) => a.code.localeCompare(b.code)),
    [sections],
  )

  const selectedGroup = React.useMemo(() => {
    if (!subjectCode) return null
    return groups.find((g) => String(g.subject_code).toUpperCase() === String(subjectCode).toUpperCase()) ?? null
  }, [groups, subjectCode])

  async function refreshRulesData(nextYear = year) {
    setLoading(true)
    try {
      const [subjs, secs, gs] = await Promise.all([
        listSubjects({ program_code: programCode, academic_year_number: nextYear }),
        listSections({ program_code: programCode, academic_year_number: nextYear }),
        listCombinedSubjectGroups({ program_code: programCode, academic_year_number: nextYear }),
      ])
      setSubjects(subjs)
      setSections(secs)
      setGroups(gs)

      // If current subject isn't valid in this year anymore, reset.
      if (subjectCode) {
        const exists = subjs.some((s) => String(s.code).toUpperCase() === String(subjectCode).toUpperCase())
        if (!exists) setSubjectCode('')
      }
    } catch (e: any) {
      showToast(`Load combined rules failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  function toggleSection(code: string) {
    setSelectedSectionCodes((prev) => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  async function saveGroup() {
    if (!subjectCode) {
      showToast('Select a THEORY subject first')
      return
    }
    const section_codes = Array.from(selectedSectionCodes)
    if (section_codes.length < 2) {
      showToast('Select at least 2 sections')
      return
    }
    setLoading(true)
    try {
      await createCombinedSubjectGroup({
        program_code: programCode,
        academic_year_number: year,
        subject_code: subjectCode,
        section_codes,
      })
      showToast('Combined rule saved')
      await refreshRulesData(year)
    } catch (e: any) {
      showToast(`Save failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function removeGroup() {
    if (!selectedGroup) return
    setLoading(true)
    try {
      await deleteCombinedSubjectGroup(selectedGroup.id)
      showToast('Combined rule deleted (future solves only)')
      setSelectedSectionCodes(new Set())
      await refreshRulesData(year)
    } catch (e: any) {
      showToast(`Delete failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function refreshRuns() {
    setLoading(true)
    try {
      const data = await listRuns({ program_code: programCode, limit: 25 })
      setRuns(data)
      if (!runId && data.length > 0) setRunId(data[0].id)
    } catch (e: any) {
      showToast(`Load runs failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  function runTag(r: any): string {
    const scope = String(r?.parameters?.scope ?? '')
    if (scope === 'PROGRAM_GLOBAL') return 'GLOBAL'
    const year = r?.parameters?.academic_year_number
    if (year != null) return `YEAR ${year}`
    return 'LEGACY'
  }

  async function analyze() {
    if (!runId) {
      showToast('Select a run first')
      return
    }
    setLoading(true)
    try {
      const entries = await listRunEntries(runId)
      const map = new Map<string, TimetableEntry[]>()
      for (const e of entries) {
        if (!e.combined_class_id) continue
        const key = String(e.combined_class_id)
        const arr = map.get(key) ?? []
        arr.push(e)
        map.set(key, arr)
      }
      const out = Array.from(map.entries())
        .map(([id, es]) => ({ id, entries: es }))
        .sort((a, b) => b.entries.length - a.entries.length)
      setAnalyzedGroups(out)
      if (out.length === 0) showToast('No combined classes found in this run')
    } catch (e: any) {
      showToast(`Analyze failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refreshRulesData(academicYearNumber)
    refreshRuns()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programCode, academicYearNumber])

  React.useEffect(() => {
    // keep local year in sync with global selection by default
    setYear(academicYearNumber)
    setSelectedSectionCodes(new Set())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [academicYearNumber])

  React.useEffect(() => {
    // When a group exists for the selected subject, mirror the selection.
    if (selectedGroup) {
      setSelectedSectionCodes(new Set(selectedGroup.sections.map((s) => s.section_code)))
    } else {
      setSelectedSectionCodes(new Set())
    }
  }, [selectedGroup])

  return (
    <div className="space-y-6">
      <Toast message={toast} />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-lg font-semibold text-slate-900">Combined Classes</div>
          <div className="mt-1 text-sm text-slate-600">Configure strict combined-subject rules, or inspect runs.</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className={`rounded-2xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${
              tab === 'rules' ? 'bg-slate-900 text-white' : 'border bg-white text-slate-800'
            }`}
            onClick={() => setTab('rules')}
            disabled={loading}
          >
            Rules
          </button>
          <button
            className={`rounded-2xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${
              tab === 'analyze' ? 'bg-slate-900 text-white' : 'border bg-white text-slate-800'
            }`}
            onClick={() => setTab('analyze')}
            disabled={loading}
          >
            Analyze
          </button>
        </div>
      </div>

      {tab === 'rules' ? (
        <>
          <div className="rounded-3xl border bg-white p-5">
            <div className="grid gap-3 md:grid-cols-[220px_1fr_auto]">
              <div>
                <div className="text-xs font-semibold text-slate-600">Academic Year</div>
                <PremiumSelect
                  ariaLabel="Academic year"
                  className="mt-1 text-sm"
                  value={String(year)}
                  onValueChange={async (v) => {
                    const nextYear = Number(v)
                    setYear(nextYear)
                    setSubjectCode('')
                    setSelectedSectionCodes(new Set())
                    await refreshRulesData(nextYear)
                  }}
                  options={[1, 2, 3].map((n) => ({ value: String(n), label: `Year ${n}` }))}
                />
              </div>

              <div>
                <div className="text-xs font-semibold text-slate-600">THEORY Subject</div>
                <PremiumSelect
                  ariaLabel="Theory subject"
                  className="mt-1"
                  value={subjectCode || '__none__'}
                  onValueChange={(v) => setSubjectCode(v === '__none__' ? '' : v)}
                  options={[
                    { value: '__none__', label: 'Select a subject…' },
                    ...theorySubjects.map((s) => ({ value: s.code, label: `${s.code} — ${s.name}` })),
                  ]}
                />
              </div>

              <div className="flex items-end justify-end gap-2">
                <button
                  className="btn-secondary disabled:opacity-50"
                  onClick={() => refreshRulesData(year)}
                  disabled={loading}
                >
                  {loading ? 'Refreshing…' : 'Refresh'}
                </button>
              </div>
            </div>

            <div className="mt-4">
              <div className="text-xs font-semibold text-slate-600">Sections (select 2+)</div>
              <div className="mt-2 grid gap-2 md:grid-cols-3">
                {activeSections.length === 0 ? (
                  <div className="rounded-2xl border bg-slate-50 p-4 text-sm text-slate-700">No sections found.</div>
                ) : (
                  activeSections.map((sec) => (
                    <label
                      key={sec.id}
                      className="checkbox-row"
                    >
                      <input
                        type="checkbox"
                        checked={selectedSectionCodes.has(sec.code)}
                        onChange={() => toggleSection(sec.code)}
                        disabled={Boolean(selectedGroup)}
                      />
                      <span className="font-semibold text-slate-900">{sec.code}</span>
                      <span className="text-slate-600">{sec.name}</span>
                    </label>
                  ))
                )}
              </div>
              {selectedGroup ? (
                <div className="mt-2 text-xs text-slate-500">
                  This subject already has a combined rule for Year {year}. Delete it to create a different one.
                </div>
              ) : null}
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-slate-500">
                Solver enforces strict combined scheduling: same slot/teacher/LT room; teacher load counted once.
              </div>
              <div className="flex items-center gap-2">
                {selectedGroup ? (
                  <button
                    className="btn-danger disabled:opacity-50"
                    onClick={removeGroup}
                    disabled={loading}
                  >
                    Delete Rule
                  </button>
                ) : (
                  <button
                    className="btn-primary disabled:opacity-50"
                    onClick={saveGroup}
                    disabled={loading || !subjectCode}
                  >
                    Save Rule
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-3xl border bg-white p-5">
            <div className="text-sm font-semibold text-slate-900">Existing Rules</div>
            <div className="mt-1 text-xs text-slate-500">Unique per (subject, academic year).</div>

            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Subject</th>
                    <th className="px-3 py-2">Sections</th>
                    <th className="px-3 py-2">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {groups.length === 0 ? (
                    <tr>
                      <td className="px-3 py-3 text-slate-700" colSpan={3}>
                        No combined rules configured.
                      </td>
                    </tr>
                  ) : (
                    groups
                      .slice()
                      .sort((a, b) => String(a.subject_code).localeCompare(String(b.subject_code)))
                      .map((g) => (
                        <tr
                          key={g.id}
                          className="cursor-pointer hover:bg-slate-50"
                          onClick={() => setSubjectCode(g.subject_code)}
                        >
                          <td className="px-3 py-2 font-medium text-slate-900">
                            {g.subject_code} <span className="font-normal text-slate-500">— {g.subject_name}</span>
                          </td>
                          <td className="px-3 py-2 text-slate-700">
                            {g.sections.map((s) => s.section_code).join(', ')}
                          </td>
                          <td className="px-3 py-2 text-slate-700">{new Date(g.created_at).toLocaleString()}</td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="rounded-3xl border bg-white p-5">
            <div className="grid gap-3 md:grid-cols-[1fr_auto]">
              <PremiumSelect
                ariaLabel="Solver run"
                className="w-full text-sm"
                searchable
                searchPlaceholder="Search runs…"
                value={runs.length === 0 ? '__none__' : runId}
                onValueChange={(v) => {
                  if (v === '__none__') return
                  setRunId(v)
                }}
                options={
                  runs.length === 0
                    ? [{ value: '__none__', label: 'No runs found', disabled: true }]
                    : runs.map((r) => ({
                        value: r.id,
                        label: `[${runTag(r)}] ${r.status} — ${new Date(r.created_at).toLocaleString()} (${r.id})`,
                      }))
                }
              />
              <button
                className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                onClick={analyze}
                disabled={loading || !runId}
              >
                Analyze
              </button>
            </div>
          </div>

          <div className="rounded-3xl border bg-white p-5">
            <div className="text-sm font-semibold text-slate-900">Groups</div>
            <div className="mt-1 text-xs text-slate-500">Only entries with a non-null combined_class_id are shown.</div>

            <div className="mt-4 space-y-3">
              {analyzedGroups.length === 0 ? (
                <div className="rounded-2xl border bg-slate-50 p-4 text-sm text-slate-700">No groups to display.</div>
              ) : (
                analyzedGroups.map((g) => (
                  <div key={g.id} className="rounded-2xl border bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-slate-900">{g.id}</div>
                      <div className="text-xs text-slate-500">{g.entries.length} entries</div>
                    </div>
                    <div className="mt-2 overflow-x-auto">
                      <table className="min-w-full text-left text-sm">
                        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-3 py-2">Section</th>
                            <th className="px-3 py-2">Subject</th>
                            <th className="px-3 py-2">Teacher</th>
                            <th className="px-3 py-2">Room</th>
                            <th className="px-3 py-2">Slot</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                          {g.entries.slice(0, 50).map((e) => (
                            <tr key={e.id} className="hover:bg-slate-50">
                              <td className="px-3 py-2 font-medium text-slate-900">{e.section_code}</td>
                              <td className="px-3 py-2 text-slate-700">{e.subject_code}</td>
                              <td className="px-3 py-2 text-slate-700">{e.teacher_code}</td>
                              <td className="px-3 py-2 text-slate-700">{e.room_code}</td>
                              <td className="px-3 py-2 text-slate-700">D{e.day_of_week} #{e.slot_index}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {g.entries.length > 50 ? (
                      <div className="mt-2 text-xs text-slate-500">Showing first 50 entries for this group.</div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
