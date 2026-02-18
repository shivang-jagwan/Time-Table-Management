import React from 'react'
import { Toast } from '../components/Toast'
import { useLayoutContext } from '../components/Layout'
import { PremiumSelect } from '../components/PremiumSelect'
import {
  createElectiveBlock,
  deleteElectiveBlock,
  deleteElectiveBlockSubject,
  listElectiveBlocks,
  setElectiveBlockSections,
  updateElectiveBlock,
  upsertElectiveBlockSubject,
  type ElectiveBlockOut,
} from '../api/admin'
import { listSections, type Section } from '../api/sections'
import { listSubjects, type Subject } from '../api/subjects'
import { listTeachers, type Teacher } from '../api/teachers'

export function ElectiveBlocks() {
  const { programCode, academicYearNumber } = useLayoutContext()

  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const [year, setYear] = React.useState<number>(academicYearNumber)
  const [subjects, setSubjects] = React.useState<Subject[]>([])
  const [teachers, setTeachers] = React.useState<Teacher[]>([])
  const [sections, setSections] = React.useState<Section[]>([])
  const [blocks, setBlocks] = React.useState<ElectiveBlockOut[]>([])

  const [selectedBlockId, setSelectedBlockId] = React.useState<string>('')

  const [editBlockName, setEditBlockName] = React.useState('')
  const [editBlockCode, setEditBlockCode] = React.useState('')
  const [editBlockActive, setEditBlockActive] = React.useState(true)

  const [newBlockName, setNewBlockName] = React.useState('')
  const [newBlockCode, setNewBlockCode] = React.useState('')

  const [assignSubjectId, setAssignSubjectId] = React.useState('')
  const [assignTeacherId, setAssignTeacherId] = React.useState('')

  const [selectedSectionIds, setSelectedSectionIds] = React.useState<Set<string>>(new Set())

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

  const activeTeachers = React.useMemo(
    () => teachers.filter((t) => t.is_active).sort((a, b) => a.code.localeCompare(b.code)),
    [teachers],
  )

  const activeSections = React.useMemo(
    () => sections.filter((s) => s.is_active).sort((a, b) => a.code.localeCompare(b.code)),
    [sections],
  )

  const selectedBlock = React.useMemo(() => {
    return blocks.find((b) => b.id === selectedBlockId) ?? null
  }, [blocks, selectedBlockId])

  React.useEffect(() => {
    if (!selectedBlock) {
      setSelectedSectionIds(new Set())
      setEditBlockName('')
      setEditBlockCode('')
      setEditBlockActive(true)
      return
    }
    setSelectedSectionIds(new Set(selectedBlock.sections.map((s) => s.section_id)))
    setEditBlockName(selectedBlock.name)
    setEditBlockCode(selectedBlock.code ?? '')
    setEditBlockActive(Boolean(selectedBlock.is_active))
  }, [selectedBlock])

  const duplicateTeacherInBlock = React.useMemo(() => {
    if (!selectedBlock || !assignTeacherId) return false
    return selectedBlock.subjects.some((s) => s.teacher_id === assignTeacherId)
  }, [selectedBlock, assignTeacherId, assignSubjectId])

  async function refresh(nextYear = year) {
    setLoading(true)
    try {
      const pc = programCode.trim()
      if (!pc) {
        const ts = await listTeachers()
        setBlocks([])
        setSubjects([])
        setSections([])
        setTeachers(ts)
        setSelectedBlockId('')
        return
      }
      const [bs, subjs, ts, secs] = await Promise.all([
        listElectiveBlocks({ program_code: pc, academic_year_number: nextYear }),
        listSubjects({ program_code: pc, academic_year_number: nextYear }),
        listTeachers(),
        listSections({ program_code: pc, academic_year_number: nextYear }),
      ])
      setBlocks(bs)
      setSubjects(subjs)
      setTeachers(ts)
      setSections(secs)

      if (selectedBlockId && !bs.some((b) => b.id === selectedBlockId)) {
        setSelectedBlockId('')
      }
    } catch (e: any) {
      showToast(`Load elective blocks failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refresh(year)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, programCode])

  async function onCreateBlock() {
    const pc = programCode.trim()
    if (!pc) {
      showToast('Select a program first', 3000)
      return
    }
    if (!newBlockName.trim()) {
      showToast('Enter block name')
      return
    }
    setLoading(true)
    try {
      const created = await createElectiveBlock({
        program_code: pc,
        academic_year_number: year,
        name: newBlockName.trim(),
        code: newBlockCode.trim() || null,
        is_active: true,
      })
      showToast('Block created')
      setNewBlockName('')
      setNewBlockCode('')
      await refresh(year)
      setSelectedBlockId(created.id)
    } catch (e: any) {
      showToast(`Create failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function onDeleteBlock() {
    if (!selectedBlock) return
    if (!confirm(`Delete elective block '${selectedBlock.name}'?`)) return
    setLoading(true)
    try {
      await deleteElectiveBlock(selectedBlock.id)
      showToast('Block deleted')
      setSelectedBlockId('')
      await refresh(year)
    } catch (e: any) {
      showToast(`Delete failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function onSaveBlockMeta() {
    if (!selectedBlock) return
    if (!editBlockName.trim()) {
      showToast('Block name cannot be empty')
      return
    }
    setLoading(true)
    try {
      await updateElectiveBlock({
        block_id: selectedBlock.id,
        academic_year_number: year,
        name: editBlockName.trim(),
        code: editBlockCode.trim() ? editBlockCode.trim() : null,
        is_active: editBlockActive,
      })
      showToast('Block updated')
      await refresh(year)
    } catch (e: any) {
      showToast(`Update failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function onUpsertAssignment() {
    if (!selectedBlock) return
    if (!assignSubjectId) {
      showToast('Select a subject')
      return
    }
    if (!assignTeacherId) {
      showToast('Select a teacher')
      return
    }
    if (duplicateTeacherInBlock) {
      showToast('Teacher already used in this block')
      return
    }
    setLoading(true)
    try {
      await upsertElectiveBlockSubject({
        block_id: selectedBlock.id,
        subject_id: assignSubjectId,
        teacher_id: assignTeacherId,
      })
      showToast('Assignment saved')
      await refresh(year)
    } catch (e: any) {
      showToast(`Save failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function onDeleteAssignment(assignmentId: string) {
    if (!selectedBlock) return
    setLoading(true)
    try {
      await deleteElectiveBlockSubject({ block_id: selectedBlock.id, assignment_id: assignmentId })
      showToast('Assignment removed')
      await refresh(year)
    } catch (e: any) {
      showToast(`Remove failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  function toggleSection(sectionId: string) {
    setSelectedSectionIds((prev) => {
      const next = new Set(prev)
      if (next.has(sectionId)) next.delete(sectionId)
      else next.add(sectionId)
      return next
    })
  }

  async function onSaveSections() {
    if (!selectedBlock) return
    setLoading(true)
    try {
      await setElectiveBlockSections({
        block_id: selectedBlock.id,
        section_ids: Array.from(selectedSectionIds),
      })
      showToast('Sections saved')
      await refresh(year)
    } catch (e: any) {
      showToast(`Save sections failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <Toast message={toast} />

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[180px]">
          <label className="mb-1 block text-xs font-semibold text-slate-700">Academic Year</label>
          <PremiumSelect
            value={String(year)}
            onValueChange={(v) => setYear(Number(v))}
            placeholder="Year"
            options={[1, 2, 3, 4].map((y) => ({ value: String(y), label: `Year ${y}` }))}
          />
        </div>

        <div className="flex-1 min-w-[240px]">
          <label className="mb-1 block text-xs font-semibold text-slate-700">Create Block</label>
          <div className="flex gap-2">
            <input
              className="input-premium flex-1"
              placeholder="Block name (e.g., Open Elective - 1)"
              value={newBlockName}
              onChange={(e) => setNewBlockName(e.target.value)}
            />
            <input
              className="input-premium w-40"
              placeholder="Code (optional)"
              value={newBlockCode}
              onChange={(e) => setNewBlockCode(e.target.value)}
            />
            <button className="btn-primary" disabled={loading} onClick={onCreateBlock}>
              Create
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-3xl border bg-white p-5 lg:col-span-1">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-900">Blocks</div>
            <button className="btn-secondary" disabled={loading} onClick={() => refresh(year)}>
              Reload
            </button>
          </div>

          <div className="space-y-1">
            {blocks.length === 0 ? (
              <div className="text-sm text-slate-600">No blocks yet.</div>
            ) : (
              blocks.map((b) => (
                <button
                  key={b.id}
                  className={
                    'w-full rounded-xl border px-3 py-2 text-left text-sm transition ' +
                    (b.id === selectedBlockId
                      ? 'border-green-300 bg-green-50'
                      : 'border-slate-200 bg-white hover:bg-slate-50')
                  }
                  onClick={() => setSelectedBlockId(b.id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-900">{b.name}</div>
                      <div className="truncate text-xs text-slate-600">
                        {b.subjects.length} subjects • {b.sections.length} sections
                      </div>
                    </div>
                    <div className="text-xs text-slate-500">{b.code ?? ''}</div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="rounded-3xl border bg-white p-5 lg:col-span-2">
          {!selectedBlock ? (
            <div className="text-sm text-slate-700">Select a block to edit.</div>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-lg font-bold text-slate-900">{selectedBlock.name}</div>
                  <div className="text-sm text-slate-600">
                    {selectedBlock.subjects.length} parallel subjects • {selectedBlock.sections.length} mapped sections
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button className="btn-secondary" disabled={loading} onClick={onSaveBlockMeta}>
                    Save Details
                  </button>
                  <button className="btn-danger" disabled={loading} onClick={onDeleteBlock}>
                    Delete Block
                  </button>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-3">
                <div className="mb-2 text-sm font-semibold text-slate-900">Block details</div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div className="md:col-span-2">
                    <label className="mb-1 block text-xs font-semibold text-slate-700">Name</label>
                    <input
                      className="input-premium w-full"
                      value={editBlockName}
                      onChange={(e) => setEditBlockName(e.target.value)}
                      placeholder="Block name"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-700">Code</label>
                    <input
                      className="input-premium w-full"
                      value={editBlockCode}
                      onChange={(e) => setEditBlockCode(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <label className="inline-flex items-center gap-2 text-sm text-slate-800">
                      <input
                        type="checkbox"
                        checked={editBlockActive}
                        onChange={(e) => setEditBlockActive(e.target.checked)}
                      />
                      Active (solver will ignore inactive blocks)
                    </label>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-3">
                <div className="mb-2 text-sm font-semibold text-slate-900">Subject → Teacher assignments</div>

                <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-700">Subject</label>
                    <PremiumSelect
                      value={assignSubjectId}
                      onValueChange={setAssignSubjectId}
                      placeholder="Select subject"
                      options={theorySubjects.map((s) => ({ value: s.id, label: `${s.code} — ${s.name}` }))}
                      searchable={theorySubjects.length >= 8}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-700">Teacher</label>
                    <PremiumSelect
                      value={assignTeacherId}
                      onValueChange={setAssignTeacherId}
                      placeholder="Select teacher"
                      options={activeTeachers.map((t) => ({ value: t.id, label: `${t.code} — ${t.full_name}` }))}
                      searchable={activeTeachers.length >= 8}
                    />
                    {duplicateTeacherInBlock ? (
                      <div className="mt-1 text-xs font-semibold text-red-600">
                        Duplicate teacher within this block is not allowed.
                      </div>
                    ) : null}
                  </div>
                  <div className="flex items-end">
                    <button
                      className="btn-primary w-full"
                      disabled={loading || duplicateTeacherInBlock}
                      onClick={onUpsertAssignment}
                    >
                      Save Assignment
                    </button>
                  </div>
                </div>

                <div className="mt-3 overflow-hidden rounded-xl border border-slate-200">
                  <table className="w-full">
                    <thead className="bg-slate-50 text-left text-xs text-slate-600">
                      <tr>
                        <th className="px-3 py-2">Subject</th>
                        <th className="px-3 py-2">Teacher</th>
                        <th className="px-3 py-2 w-24">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedBlock.subjects.length === 0 ? (
                        <tr>
                          <td className="px-3 py-3 text-sm text-slate-600" colSpan={3}>
                            No assignments yet.
                          </td>
                        </tr>
                      ) : (
                        selectedBlock.subjects.map((s) => (
                          <tr key={s.id} className="border-t border-slate-200">
                            <td className="px-3 py-2 text-sm text-slate-900">
                              <div className="font-semibold">{s.subject_code}</div>
                              <div className="text-xs text-slate-600">{s.subject_name}</div>
                            </td>
                            <td className="px-3 py-2 text-sm text-slate-900">
                              <div className="font-semibold">{s.teacher_code ?? ''}</div>
                              <div className="text-xs text-slate-600">{s.teacher_name ?? ''}</div>
                            </td>
                            <td className="px-3 py-2">
                              <button
                                className="btn-secondary"
                                disabled={loading}
                                onClick={() => onDeleteAssignment(s.id)}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-900">Map sections to this block</div>
                  <button className="btn-primary" disabled={loading} onClick={onSaveSections}>
                    Save Sections
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {activeSections.map((s) => (
                    <label
                      key={s.id}
                      className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={selectedSectionIds.has(s.id)}
                        onChange={() => toggleSection(s.id)}
                      />
                      <span className="font-semibold">{s.code}</span>
                      <span className="text-slate-600 truncate">{s.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
