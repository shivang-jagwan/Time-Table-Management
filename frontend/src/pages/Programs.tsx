import React from 'react'
import { createProgram, deleteProgram, listPrograms, type Program } from '../api/programs'
import { ensureAcademicYears, listAcademicYears, mapProgramDataToYear, type AcademicYearOut } from '../api/admin'
import { Toast } from '../components/Toast'

export function Programs() {
  const [toast, setToast] = React.useState('')
  const [items, setItems] = React.useState<Program[]>([])
  const [years, setYears] = React.useState<AcademicYearOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [query, setQuery] = React.useState('')
  const [code, setCode] = React.useState('')
  const [name, setName] = React.useState('')
  const [saving, setSaving] = React.useState(false)

  const [yearLoading, setYearLoading] = React.useState(false)
  const [mapProgramCode, setMapProgramCode] = React.useState('')
  const [fromYear, setFromYear] = React.useState(1)
  const [toYear, setToYear] = React.useState(3)
  const [replaceTarget, setReplaceTarget] = React.useState(true)
  const [mapping, setMapping] = React.useState(false)

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function refresh() {
    setLoading(true)
    try {
      const data = await listPrograms()
      setItems(data)
    } catch (e: any) {
      showToast(`Load failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function refreshYears() {
    setYearLoading(true)
    try {
      const data = await listAcademicYears()
      setYears(data)
    } catch (e: any) {
      showToast(`Load years failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setYearLoading(false)
    }
  }

  React.useEffect(() => {
    refresh()
    refreshYears()
  }, [])

  React.useEffect(() => {
    // Default the mapping dropdown to the first existing program.
    if (!mapProgramCode && items.length > 0) setMapProgramCode(items[0].code)
  }, [items, mapProgramCode])

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter((p) =>
      `${p.code} ${p.name}`.toLowerCase().includes(q),
    )
  }, [items, query])

  async function onCreate(e: React.FormEvent) {
    e.preventDefault()
    const c = code.trim()
    const n = name.trim()
    if (!c || !n) {
      showToast('Code and name are required', 3000)
      return
    }
    setSaving(true)
    try {
      await createProgram({ code: c, name: n })
      setCode('')
      setName('')
      showToast('Program created')
      await refresh()
    } catch (e: any) {
      showToast(`Create failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setSaving(false)
    }
  }

  async function onDelete(p: Program) {
    if (!confirm(`Delete program ${p.code}?`)) return
    try {
      await deleteProgram(p.id)
      showToast('Program deleted')
      await refresh()
    } catch (e: any) {
      showToast(`Delete failed: ${String(e?.message ?? e)}`, 3500)
    }
  }

  async function onEnsureYears() {
    setYearLoading(true)
    try {
      const result = await ensureAcademicYears({ year_numbers: [1, 2, 3, 4], activate: true })
      showToast(`Years ensured (created: ${result.created}, updated: ${result.updated})`)
      await refreshYears()
    } catch (e: any) {
      showToast(`Ensure years failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setYearLoading(false)
    }
  }

  async function onMapToYear3(e: React.FormEvent) {
    e.preventDefault()
    const pc = mapProgramCode.trim()
    if (!pc) {
      showToast('Select a program to map', 3000)
      return
    }
    if (fromYear === toYear) {
      showToast('From year and to year must be different', 3000)
      return
    }

    if (
      !confirm(
        `Map program ${pc} data from Year ${fromYear} to Year ${toYear}?` +
          (replaceTarget ? `\n\nThis will delete any existing Year ${toYear} data for ${pc} first.` : ''),
      )
    ) {
      return
    }

    setMapping(true)
    try {
      const res = await mapProgramDataToYear({
        program_code: pc,
        from_academic_year_number: fromYear,
        to_academic_year_number: toYear,
        replace_target: replaceTarget,
      })
      const updatedTotal = Object.values(res.updated ?? {}).reduce((a, b) => a + (Number(b) || 0), 0)
      const deletedTotal = Object.values(res.deleted ?? {}).reduce((a, b) => a + (Number(b) || 0), 0)
      showToast(`Mapped. Updated ${updatedTotal} rows${replaceTarget ? `, deleted ${deletedTotal} rows` : ''}.`, 4000)
      await refreshYears()
    } catch (e: any) {
      showToast(`Map failed: ${String(e?.message ?? e)}`, 4500)
    } finally {
      setMapping(false)
    }
  }

  async function onQuickMap(programCode: string) {
    const pc = programCode.trim()
    if (!pc) return
    if (fromYear === toYear) {
      showToast('From year and to year must be different', 3000)
      return
    }

    if (
      !confirm(
        `Map program ${pc} data from Year ${fromYear} to Year ${toYear}?` +
          (replaceTarget ? `\n\nThis will delete any existing Year ${toYear} data for ${pc} first.` : ''),
      )
    ) {
      return
    }

    setMapping(true)
    try {
      const res = await mapProgramDataToYear({
        program_code: pc,
        from_academic_year_number: fromYear,
        to_academic_year_number: toYear,
        replace_target: replaceTarget,
      })
      const updatedTotal = Object.values(res.updated ?? {}).reduce((a, b) => a + (Number(b) || 0), 0)
      const deletedTotal = Object.values(res.deleted ?? {}).reduce((a, b) => a + (Number(b) || 0), 0)
      showToast(`Mapped ${pc}. Updated ${updatedTotal} rows${replaceTarget ? `, deleted ${deletedTotal} rows` : ''}.`, 4500)
      await refreshYears()
    } catch (e: any) {
      showToast(`Map failed: ${String(e?.message ?? e)}`, 4500)
    } finally {
      setMapping(false)
    }
  }

  return (
    <div className="space-y-6">
      <Toast message={toast} />

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Programs</h1>
          <p className="mt-1 text-sm text-slate-600">Manage program codes used across subjects, sections, and curriculum.</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <form onSubmit={onCreate} className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className="text-xs font-medium text-slate-600">Code</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="e.g. CSE"
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-xs font-medium text-slate-600">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Computer Science & Engineering"
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            />
          </div>
          <div className="md:col-span-3 flex items-center justify-end">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {saving ? 'Creating…' : 'Create Program'}
            </button>
          </div>
        </form>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">Academic Years</div>
            <div className="mt-1 text-xs text-slate-600">These must exist for Subjects/Sections/Curriculum pages to work.</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refreshYears}
              type="button"
              disabled={yearLoading}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {yearLoading ? 'Loading…' : 'Refresh'}
            </button>
            <button
              onClick={onEnsureYears}
              type="button"
              disabled={yearLoading}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              Ensure Years 1–4
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {years.length === 0 ? (
            <div className="text-sm text-slate-600">No academic years found yet.</div>
          ) : (
            years.map((y) => (
              <div
                key={y.id}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800"
              >
                Year {y.year_number}
                <span className={y.is_active ? 'text-emerald-700' : 'text-slate-500'}>
                  {y.is_active ? ' · active' : ' · inactive'}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="text-sm font-semibold text-slate-900">Map Existing Data to Year 3</div>
        <div className="mt-1 text-xs text-slate-600">
          Use this when you imported old data and want it to appear under Year 3.
        </div>

        <form onSubmit={onMapToYear3} className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="map_program">
              Program
            </label>
            <select
              id="map_program"
              value={mapProgramCode}
              onChange={(e) => setMapProgramCode(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            >
              {items.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.code}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="map_from_year">
              From Year
            </label>
            <select
              id="map_from_year"
              value={String(fromYear)}
              onChange={(e) => setFromYear(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="map_to_year">
              To Year
            </label>
            <select
              id="map_to_year"
              value={String(toYear)}
              onChange={(e) => setToYear(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-end justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={replaceTarget}
                onChange={(e) => setReplaceTarget(e.target.checked)}
              />
              Replace target year first
            </label>

            <button
              type="submit"
              disabled={mapping || items.length === 0}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {mapping ? 'Mapping…' : 'Map'}
            </button>
          </div>
        </form>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search programs…"
            className="w-full max-w-md rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
          />
          <button
            onClick={refresh}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td className="px-4 py-4 text-slate-600" colSpan={3}>Loading…</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td className="px-4 py-4 text-slate-600" colSpan={3}>No programs found.</td>
                </tr>
              ) : (
                filtered.map((p) => (
                  <tr key={p.code} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-900">{p.code}</td>
                    <td className="px-4 py-3 text-slate-700">{p.name}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => {
                          setMapProgramCode(p.code)
                          void onQuickMap(p.code)
                        }}
                        disabled={mapping}
                        title={`Map ${p.code} data to Year ${toYear}`}
                        className="mr-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-50"
                      >
                        Map → Year {toYear}
                      </button>
                      <button
                        onClick={() => onDelete(p)}
                        className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-100"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
