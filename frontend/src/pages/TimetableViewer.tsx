import React from 'react'
import {
  listRuns,
  listRunEntries,
  listTimeSlots,
  listFixedEntries,
  listSectionRequiredSubjects,
  RunSummary,
  TimetableEntry,
  TimeSlot,
  FixedTimetableEntry,
  RequiredSubject,
} from '../api/solver'
import { PremiumSelect } from '../components/PremiumSelect'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function yearFromSectionCode(code: string): number | null {
  const m = /^Y(\d+)\b/i.exec(String(code ?? '').trim())
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) ? n : null
}

function shortId(id: string): string {
  return id.split('-')[0] ?? id
}

function buildCellMap(entries: TimetableEntry[]) {
  const map = new Map<string, TimetableEntry[]>()
  for (const e of entries) {
    const key = `${e.day_of_week}:${e.slot_index}`
    const arr = map.get(key) ?? []
    arr.push(e)
    map.set(key, arr)
  }
  return map
}

function groupForCell(entries: TimetableEntry[]) {
  const nonElective: TimetableEntry[] = []
  const electiveByBlock = new Map<string, { name: string; items: TimetableEntry[] }>()

  for (const e of entries) {
    const blockId = (e as any).elective_block_id as string | undefined
    if (!blockId) {
      nonElective.push(e)
      continue
    }
    const name = String((e as any).elective_block_name ?? 'Elective Block')
    const group = electiveByBlock.get(blockId) ?? { name, items: [] }
    group.items.push(e)
    electiveByBlock.set(blockId, group)
  }

  const electiveGroups = Array.from(electiveByBlock.entries())
    .sort((a, b) => a[1].name.localeCompare(b[1].name))
    .map(([blockId, g]) => ({ blockId, name: g.name, items: g.items }))

  nonElective.sort((a, b) => `${a.subject_code}-${a.teacher_code}`.localeCompare(`${b.subject_code}-${b.teacher_code}`))
  for (const g of electiveGroups) {
    g.items.sort((a, b) => `${a.subject_code}-${a.teacher_code}`.localeCompare(`${b.subject_code}-${b.teacher_code}`))
  }

  return { nonElective, electiveGroups }
}

export function TimetableViewer({ onToast }: { onToast: (msg: string) => void }) {
  const [loading, setLoading] = React.useState(false)
  const [programCode, setProgramCode] = React.useState('CSE')
  const [academicYearNumber, setAcademicYearNumber] = React.useState(3)
  const [runScopeFilter, setRunScopeFilter] = React.useState<'ALL' | 'PROGRAM_GLOBAL' | 'YEAR_ONLY'>(
    'PROGRAM_GLOBAL',
  )

  const [runs, setRuns] = React.useState<RunSummary[]>([])
  const [runId, setRunId] = React.useState<string>('')

  const [slots, setSlots] = React.useState<TimeSlot[]>([])
  const [entries, setEntries] = React.useState<TimetableEntry[]>([])

  const [fixedEntries, setFixedEntries] = React.useState<FixedTimetableEntry[]>([])
  const [requiredSubjects, setRequiredSubjects] = React.useState<RequiredSubject[]>([])

  const [sectionCode, setSectionCode] = React.useState<string>('')

  const selectedSectionId = React.useMemo(() => {
    if (!sectionCode) return ''
    return entries.find((e) => e.section_code === sectionCode)?.section_id ?? ''
  }, [entries, sectionCode])

  const sectionCodes = React.useMemo(() => {
    const set = new Set(entries.map((e) => e.section_code))
    return Array.from(set).sort()
  }, [entries])

  const sectionCodesForYear = React.useMemo(() => {
    const yn = Number(academicYearNumber)
    return sectionCodes.filter((c) => {
      const y = yearFromSectionCode(c)
      return y == null || y === yn
    })
  }, [sectionCodes, academicYearNumber])

  React.useEffect(() => {
    if (!sectionCode) return
    if (sectionCodesForYear.length === 0) return
    if (!sectionCodesForYear.includes(sectionCode)) {
      setSectionCode('')
    }
  }, [sectionCode, sectionCodesForYear])

  const slotIndices = React.useMemo(() => {
    const set = new Set<number>()
    for (const s of slots) set.add(s.slot_index)
    return Array.from(set).sort((a, b) => a - b)
  }, [slots])

  const timeLabelByIndex = React.useMemo(() => {
    const map = new Map<number, string>()
    // assume same time range across days; pick first occurrence
    for (const s of slots) {
      if (!map.has(s.slot_index)) {
        map.set(s.slot_index, `${s.start_time}–${s.end_time}`)
      }
    }
    return map
  }, [slots])

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
      const data = await listRuns({ program_code: programCode.trim(), limit: 50 })
      setRuns(data)
      if (data.length && !runId) setRunId(data[0].id)
      onToast(`Loaded ${data.length} runs`)
    } catch (e: any) {
      onToast(`Runs load failed: ${String(e?.message ?? e)}`)
    } finally {
      setLoading(false)
      setTimeout(() => onToast(''), 2500)
    }
  }

  async function refreshSlots() {
    try {
      const data = await listTimeSlots()
      setSlots(data)
    } catch (e: any) {
      onToast(`Time slots load failed: ${String(e?.message ?? e)}`)
      setTimeout(() => onToast(''), 3000)
    }
  }

  async function refreshEntries(selectedRunId: string, selectedSectionCode?: string) {
    setLoading(true)
    try {
      const data = await listRunEntries(selectedRunId, selectedSectionCode || undefined)
      setEntries(data)
      onToast(`Loaded ${data.length} entries`)
    } catch (e: any) {
      onToast(`Entries load failed: ${String(e?.message ?? e)}`)
    } finally {
      setLoading(false)
      setTimeout(() => onToast(''), 2500)
    }
  }

  React.useEffect(() => {
    refreshSlots()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  React.useEffect(() => {
    refreshRuns()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  React.useEffect(() => {
    if (!runId) return
    // load all entries for the run first so we can populate section list
    refreshEntries(runId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  React.useEffect(() => {
    if (!selectedSectionId) {
      setFixedEntries([])
      setRequiredSubjects([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const [fe, subj] = await Promise.all([
          listFixedEntries({ section_id: selectedSectionId }),
          listSectionRequiredSubjects({ section_id: selectedSectionId }),
        ])
        if (cancelled) return
        setFixedEntries(fe)
        setRequiredSubjects(subj)
      } catch (e: any) {
        if (!cancelled) onToast(`Fixed slots load failed: ${String(e?.message ?? e)}`)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedSectionId, onToast])

  const filteredEntries = React.useMemo(() => {
    if (!sectionCode) return entries
    return entries.filter((e) => e.section_code === sectionCode)
  }, [entries, sectionCode])

  const cellMap = React.useMemo(() => buildCellMap(filteredEntries), [filteredEntries])

  const fixedByCell = React.useMemo(() => {
    if (!selectedSectionId) return new Map<string, { entry: FixedTimetableEntry; isStart: boolean }>()
    const subjById = new Map(requiredSubjects.map((s) => [s.id, s]))
    const map = new Map<string, { entry: FixedTimetableEntry; isStart: boolean }>()
    for (const e of fixedEntries.filter((x) => x.is_active)) {
      const baseKey = `${e.day_of_week}:${e.slot_index}`
      map.set(baseKey, { entry: e, isStart: true })

      if (String(e.subject_type) === 'LAB') {
        const subj = subjById.get(e.subject_id)
        const block = Number(subj?.lab_block_size_slots ?? 1)
        if (block > 1) {
          for (let j = 1; j < block; j++) {
            map.set(`${e.day_of_week}:${e.slot_index + j}`, { entry: e, isStart: false })
          }
        }
      }
    }
    return map
  }, [fixedEntries, requiredSubjects, selectedSectionId])

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <div>
          <label className="text-xs font-medium text-slate-600" htmlFor="tt_program">
            Program
          </label>
          <input
            id="tt_program"
            className="input-premium mt-1 w-full text-sm"
            value={programCode}
            onChange={(e) => setProgramCode(e.target.value)}
            placeholder="CSE"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600" htmlFor="tt_year">
            Year
          </label>
          <PremiumSelect
            id="tt_year"
            ariaLabel="Academic year"
            className="mt-1 text-sm"
            value={String(academicYearNumber)}
            onValueChange={(v) => setAcademicYearNumber(Number(v))}
            options={[
              { value: '1', label: 'Year 1' },
              { value: '2', label: 'Year 2' },
              { value: '3', label: 'Year 3' },
            ]}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600" htmlFor="tt_scope">
            Scope
          </label>
          <PremiumSelect
            id="tt_scope"
            ariaLabel="Run scope"
            className="mt-1 text-sm"
            value={runScopeFilter}
            onValueChange={(v) => setRunScopeFilter(v as any)}
            options={[
              { value: 'PROGRAM_GLOBAL', label: 'Program Global' },
              { value: 'YEAR_ONLY', label: 'This Year Only' },
              { value: 'ALL', label: 'All' },
            ]}
          />
        </div>
        <div className="flex items-end gap-2 md:col-span-3">
          <button
            className="btn-secondary w-full px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-50"
            onClick={refreshRuns}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh Runs'}
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="text-xs font-medium text-slate-600" htmlFor="tt_run">
            Run
          </label>
          <PremiumSelect
            id="tt_run"
            ariaLabel="Run"
            className="mt-1 text-sm"
            searchable
            searchPlaceholder="Search runs…"
            value={runId || '__none__'}
            onValueChange={(v) => setRunId(v === '__none__' ? '' : v)}
            options={[
              { value: '__none__', label: 'Select…' },
              ...visibleRuns.map((r) => ({
                value: r.id,
                label: `[${runTag(r)}] ${shortId(r.id)} • ${r.status} • ${new Date(r.created_at).toLocaleString()}`,
              })),
            ]}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600" htmlFor="tt_section">
            Section
          </label>
          <PremiumSelect
            id="tt_section"
            ariaLabel="Section"
            className="mt-1 text-sm"
            disabled={!entries.length}
            value={sectionCode || '__all__'}
            onValueChange={(v) => setSectionCode(v === '__all__' ? '' : v)}
            options={[
              { value: '__all__', label: 'All sections' },
              ...sectionCodesForYear.map((c) => ({ value: c, label: c })),
            ]}
          />
        </div>
      </div>

      <div className="rounded-2xl border bg-white p-3">
        <div className="flex items-center justify-between gap-2 px-1 pb-3">
          <div className="text-sm font-semibold text-slate-900">Timetable</div>
          <button
            className="btn-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            onClick={() => (runId ? refreshEntries(runId, undefined) : null)}
            disabled={loading || !runId}
          >
            {loading ? 'Loading…' : 'Reload Entries'}
          </button>
        </div>

        {slotIndices.length === 0 ? (
          <div className="text-sm text-slate-600">No time slots configured.</div>
        ) : (
          <div className="overflow-auto">
            <table className="min-w-full border-separate border-spacing-0">
              <thead>
                <tr>
                  <th className="sticky left-0 z-10 border-b bg-white px-3 py-2 text-left text-xs font-semibold text-slate-700">
                    Day
                  </th>
                  {slotIndices.map((idx) => (
                    <th
                      key={idx}
                      className="border-b bg-white px-3 py-2 text-left text-xs font-semibold text-slate-700"
                    >
                      <div>Slot {idx + 1}</div>
                      <div className="text-[11px] font-normal text-slate-500">
                        {timeLabelByIndex.get(idx) ?? ''}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {WEEKDAYS.map((dayName, day) => (
                  <tr key={dayName}>
                    <td className="sticky left-0 z-10 border-b bg-white px-3 py-2 text-xs font-semibold text-slate-800">
                      {dayName}
                    </td>
                    {slotIndices.map((idx) => {
                      const key = `${day}:${idx}`
                      const cell = cellMap.get(key) ?? []
                      const grouped = groupForCell(cell)
                      const fixedInfo = fixedByCell.get(key) ?? null
                      return (
                        <td
                          key={key}
                          className={
                            'border-b px-2 py-2 align-top ' +
                            (fixedInfo ? 'bg-amber-50' : '')
                          }
                        >
                          {cell.length === 0 ? (
                            fixedInfo ? (
                              <div className="rounded-lg border border-amber-200 bg-white px-2 py-1">
                                <div className="text-xs font-semibold text-slate-900">
                                  🔒 {fixedInfo.entry.subject_code}{' '}
                                  <span className="text-slate-500">({fixedInfo.entry.subject_type})</span>
                                </div>
                                <div className="text-[11px] text-slate-600">
                                  {fixedInfo.entry.teacher_code} • {fixedInfo.entry.room_code}
                                </div>
                                {!fixedInfo.isStart ? (
                                  <div className="text-[11px] text-slate-500">(lab block continuation)</div>
                                ) : null}
                              </div>
                            ) : (
                              <div className="h-10 rounded-lg bg-slate-50" />
                            )
                          ) : (
                            <div className="space-y-1">
                              {grouped.electiveGroups.map((g) => (
                                <div key={g.blockId} className="rounded-lg border bg-indigo-50 px-2 py-1">
                                  <div className="text-xs font-semibold text-slate-900">
                                    {fixedInfo ? '🔒 ' : ''}🎓 {g.name}
                                    <span className="ml-1 text-slate-500">({g.items.length} parallel)</span>
                                  </div>
                                  <div className="mt-0.5 space-y-0.5">
                                    {g.items.slice(0, 3).map((e) => (
                                      <div key={e.id} className="text-[11px] text-slate-700">
                                        {e.subject_code} • {e.teacher_code} • {e.room_code}
                                      </div>
                                    ))}
                                    {g.items.length > 3 ? (
                                      <div className="text-[11px] text-slate-500">+{g.items.length - 3} more</div>
                                    ) : null}
                                  </div>
                                </div>
                              ))}

                              {grouped.nonElective.slice(0, 3).map((e) => (
                                <div key={e.id} className="rounded-lg border bg-slate-50 px-2 py-1">
                                  <div className="text-xs font-semibold text-slate-900">
                                    {fixedInfo ? '🔒 ' : ''}
                                    {e.subject_code}
                                  </div>
                                  <div className="text-[11px] text-slate-600">
                                    {e.teacher_code} • {e.room_code}
                                  </div>
                                </div>
                              ))}

                              {grouped.nonElective.length > 3 ? (
                                <div className="text-[11px] text-slate-500">
                                  +{grouped.nonElective.length - 3} more
                                </div>
                              ) : null}
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
