import React from 'react'
import { Toast } from '../components/Toast'
import { useLayoutContext } from '../components/Layout'
import { PremiumSelect } from '../components/PremiumSelect'
import { listTrackSubjects } from '../api/curriculum'
import { listSubjects, type Subject } from '../api/subjects'
import { listSections } from '../api/sections'
import {
  bulkSetCoreElective,
  listSectionElectives,
  setSectionElective,
  type SectionElectiveAssignment,
} from '../api/admin'

type ElectiveOption = {
  code: string
  name: string
}

export function Electives() {
  const { programCode, academicYearNumber } = useLayoutContext()
  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const [options, setOptions] = React.useState<ElectiveOption[]>([])
  const [assignments, setAssignments] = React.useState<SectionElectiveAssignment[]>([])
  const [sectionCodes, setSectionCodes] = React.useState<string[]>([])

  const [selectionBySection, setSelectionBySection] = React.useState<Record<string, string>>({})

  const [bulkSubjectCode, setBulkSubjectCode] = React.useState('')
  const [bulkReplace, setBulkReplace] = React.useState(true)

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function refresh() {
    setLoading(true)
    try {
      const pc = programCode.trim()
      if (!pc) {
        setOptions([])
        setAssignments([])
        setSectionCodes([])
        setSelectionBySection({})
        setBulkSubjectCode('')
        return
      }
      const [sections, subjects, trackRows, current] = await Promise.all([
        listSections({ program_code: pc, academic_year_number: academicYearNumber }),
        listSubjects({ program_code: pc, academic_year_number: academicYearNumber }),
        listTrackSubjects({ program_code: pc, academic_year_number: academicYearNumber }),
        listSectionElectives({ program_code: pc, academic_year_number: academicYearNumber }),
      ])

      const subjectById = new Map(subjects.map((s) => [s.id, s] as const))

      const electiveSubjects: Subject[] = trackRows
        .filter((r) => r.track === 'CORE' && r.is_elective)
        .map((r) => subjectById.get(r.subject_id))
        .filter(Boolean) as Subject[]

      const opt = electiveSubjects
        .map((s) => ({ code: s.code, name: s.name }))
        .sort((a, b) => a.code.localeCompare(b.code))

      setOptions(opt)
      setAssignments(current)
      setSectionCodes(
        sections
          .filter((s) => s.track === 'CORE' && s.is_active)
          .map((s) => s.code)
          .sort(),
      )

      if (bulkSubjectCode === '' && opt.length > 0) {
        setBulkSubjectCode(opt[0].code)
      }

      // Initialize dropdown selections
      const currentBySection = new Map(current.map((a) => [a.section_code, a.subject_code ?? ''] as const))
      const defaultCode = opt[0]?.code ?? ''
      setSelectionBySection((prev) => {
        const next: Record<string, string> = { ...prev }
        for (const s of sections.filter((x) => x.track === 'CORE' && x.is_active).map((x) => x.code)) {
          const existing = currentBySection.get(s)
          next[s] = (existing && existing.length > 0 ? existing : next[s] || defaultCode) || ''
        }
        return next
      })
    } catch (e: any) {
      showToast(`Load failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programCode, academicYearNumber])

  const assignmentBySection = React.useMemo(() => {
    const map = new Map<string, SectionElectiveAssignment>()
    for (const a of assignments) map.set(a.section_code, a)
    return map
  }, [assignments])

  async function onSaveSection(section_code: string, subject_code: string) {
    try {
      const pc = programCode.trim()
      if (!pc) {
        showToast('Select a program first', 3000)
        return
      }
      await setSectionElective({ program_code: pc, academic_year_number: academicYearNumber, section_code, subject_code })
      showToast(`Saved elective for ${section_code}`)
      await refresh()
    } catch (e: any) {
      showToast(`Save failed: ${String(e?.message ?? e)}`, 3500)
    }
  }

  async function onBulkSet() {
    const pc = programCode.trim()
    if (!pc) {
      showToast('Select a program first', 3000)
      return
    }
    if (!bulkSubjectCode) {
      showToast('Choose an elective subject first')
      return
    }
    if (!confirm(`Set ${bulkSubjectCode} as elective for all CORE sections?`)) return
    try {
      await bulkSetCoreElective({
        program_code: pc,
        academic_year_number: academicYearNumber,
        subject_code: bulkSubjectCode,
        replace_existing: bulkReplace,
      })
      showToast('Bulk elective set')
      await refresh()
    } catch (e: any) {
      showToast(`Bulk set failed: ${String(e?.message ?? e)}`, 3500)
    }
  }

  return (
    <div className="space-y-6">
      <Toast message={toast} />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-lg font-semibold text-slate-900">Electives (CORE)</div>
          <div className="mt-1 text-sm text-slate-600">
            Choose which CORE elective subject each CORE section will take for {programCode} year {academicYearNumber}.
          </div>
        </div>
        <button
          className="btn-secondary text-sm font-medium text-slate-800 disabled:opacity-50"
          onClick={refresh}
          disabled={loading}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="rounded-3xl border bg-white p-5">
        <div className="text-sm font-semibold text-slate-900">Bulk set</div>
        <div className="mt-1 text-xs text-slate-500">
          Applies to all CORE sections. Options are taken from Curriculum → CORE rows marked as elective.
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto]">
          <PremiumSelect
            value={bulkSubjectCode}
            onValueChange={(v) => setBulkSubjectCode(v)}
            ariaLabel="Bulk elective subject"
            placeholder={options.length === 0 ? 'No CORE electives configured' : 'Select…'}
            disabled={options.length === 0}
            options={options.map((o) => ({ value: o.code, label: `${o.code} — ${o.name}` }))}
          />

          <label className="checkbox-row rounded-lg border border-white/40 bg-white/70">
            <input
              type="checkbox"
              checked={bulkReplace}
              aria-label="Replace existing"
              onChange={(e) => setBulkReplace(e.target.checked)}
            />
            <span className="text-slate-700 font-medium">Replace existing</span>
          </label>

          <button
            className="btn-primary text-sm font-semibold disabled:opacity-50"
            disabled={loading || options.length === 0}
            onClick={onBulkSet}
          >
            Bulk set
          </button>
        </div>
      </div>

      <div className="rounded-3xl border bg-white p-5">
        <div className="text-sm font-semibold text-slate-900">Per-section selection</div>
        <div className="mt-1 text-xs text-slate-500">
          Only CORE sections appear here.
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Section</th>
                <th className="px-4 py-3">Current elective</th>
                <th className="px-4 py-3">Set elective</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {sectionCodes.length === 0 ? (
                <tr>
                  <td className="px-4 py-4 text-slate-600" colSpan={4}>
                    No CORE sections found.
                  </td>
                </tr>
              ) : (
                sectionCodes.map((sectionCode) => {
                  const a = assignmentBySection.get(sectionCode)
                  const value = selectionBySection[sectionCode] ?? ''
                  return (
                    <tr key={sectionCode} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-900">{sectionCode}</td>
                      <td className="px-4 py-3 text-slate-700">
                        {a?.subject_code ? `${a.subject_code} — ${a.subject_name ?? ''}` : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <PremiumSelect
                          value={value}
                          onValueChange={(v) => setSelectionBySection((m) => ({ ...m, [sectionCode]: v }))}
                          ariaLabel={`Elective for ${sectionCode}`}
                          placeholder={options.length === 0 ? 'No CORE electives configured' : 'Select…'}
                          disabled={options.length === 0}
                          options={options.map((o) => ({ value: o.code, label: `${o.code} — ${o.name}` }))}
                        />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          className="btn-primary text-sm font-semibold disabled:opacity-50"
                          disabled={!value || options.length === 0}
                          onClick={() => onSaveSection(sectionCode, value)}
                        >
                          Save
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
