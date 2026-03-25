import React from 'react'
import { useLayoutContext } from '../components/Layout'
import { Toast } from '../components/Toast'
import { PremiumSelect } from '../components/PremiumSelect'
import {
  listCombinedSubjectGroups,
  listTeacherSubjectSections,
  type CombinedSubjectGroupOut,
  type TeacherSubjectSectionAssignmentRow,
} from '../api/admin'
import { listSections, type Section } from '../api/sections'
import { listRooms, type Room } from '../api/rooms'
import { getTeacherTimeWindows, listTeachers, type Teacher, type TeacherTimeWindow } from '../api/teachers'
import { listSubjects, type Subject } from '../api/subjects'
import {
  listTimeSlots,
  listSpecialAllotments,
  upsertSpecialAllotment,
  deleteSpecialAllotment,
  type TimeSlot,
  type SpecialAllotment,
} from '../api/solver'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function slotLabel(s: TimeSlot) {
  const d = WEEKDAYS[s.day_of_week] ?? `D${s.day_of_week}`
  return `${d} #${s.slot_index} (${s.start_time}-${s.end_time})`
}

export function SpecialAllotments() {
  const { programCode, academicYearNumber } = useLayoutContext()

  const [toast, setToast] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const [sections, setSections] = React.useState<Section[]>([])

  const [slots, setSlots] = React.useState<TimeSlot[]>([])
  const [subjects, setSubjects] = React.useState<Subject[]>([])
  const [rooms, setRooms] = React.useState<Room[]>([])
  const [teachers, setTeachers] = React.useState<Teacher[]>([])
  const [combinedGroups, setCombinedGroups] = React.useState<CombinedSubjectGroupOut[]>([])
  const [teacherSubjectRows, setTeacherSubjectRows] = React.useState<TeacherSubjectSectionAssignmentRow[]>([])
  const [teacherWindows, setTeacherWindows] = React.useState<TeacherTimeWindow[]>([])

  const [entries, setEntries] = React.useState<SpecialAllotment[]>([])
  const [teacherId, setTeacherId] = React.useState('')

  const [saving, setSaving] = React.useState(false)
  const [form, setForm] = React.useState<{ slot_id: string; subject_id: string; target_key: string; room_id: string; reason: string }>(
    { slot_id: '', subject_id: '', target_key: '', room_id: '', reason: '' },
  )

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function refreshBase() {
    setLoading(true)
    try {
      const shouldLoadSections = Boolean(programCode) && Boolean(academicYearNumber)
      const [sec, ts, r, t, subjs, groups] = await Promise.all([
        shouldLoadSections
          ? listSections({ program_code: programCode, academic_year_number: academicYearNumber })
          : Promise.resolve([]),
        listTimeSlots(),
        listRooms(),
        listTeachers(),
        shouldLoadSections
          ? listSubjects({ program_code: programCode, academic_year_number: academicYearNumber })
          : Promise.resolve([]),
        shouldLoadSections
          ? listCombinedSubjectGroups({ program_code: programCode, academic_year_number: academicYearNumber })
          : Promise.resolve([]),
      ])
      if (!shouldLoadSections) {
        setSections([])
        setSubjects([])
        setCombinedGroups([])
        showToast('Select program + year first (top bar)', 3500)
      } else {
        setSections(sec.filter((x) => Boolean(x.is_active)))
        setSubjects(subjs.filter((x) => Boolean(x.is_active)))
        setCombinedGroups(groups)
      }
      setSlots(ts)
      setRooms(r.filter((x) => Boolean(x.is_active)))
      setTeachers(t.filter((x) => Boolean(x.is_active)))
      setTeacherSubjectRows([])
      setTeacherId('')
      setEntries([])
      setForm({ slot_id: '', subject_id: '', target_key: '', room_id: '', reason: '' })
    } catch (e: any) {
      showToast(`Load failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function refreshTeacherData(selectedTeacherId: string) {
    if (!selectedTeacherId) {
      setTeacherSubjectRows([])
      setEntries([])
      setTeacherWindows([])
      return
    }
    setLoading(true)
    try {
      const [rows, sa, tw] = await Promise.all([
        listTeacherSubjectSections({ teacher_id: selectedTeacherId }),
        listSpecialAllotments({ teacher_id: selectedTeacherId }),
        getTeacherTimeWindows(selectedTeacherId),
      ])
      setTeacherSubjectRows(rows)
      setEntries(sa)
      setTeacherWindows(tw.windows ?? [])
    } catch (e: any) {
      showToast(`Load failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refreshBase()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programCode, academicYearNumber])

  React.useEffect(() => {
    refreshTeacherData(teacherId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teacherId])

  function onSubjectChange(subjectId: string) {
    setForm((f) => ({ ...f, subject_id: subjectId, target_key: '' }))
  }

  async function onSave() {
    if (!teacherId) {
      showToast('Pick a teacher', 2500)
      return
    }
    if (!form.subject_id || !form.target_key || !form.room_id) {
      showToast('Pick subject, target, and room', 2500)
      return
    }

    setSaving(true)
    try {
      const sectionId = form.target_key.startsWith('S:') ? form.target_key.slice(2) : undefined
      const combinedGroupId = form.target_key.startsWith('C:') ? form.target_key.slice(2) : undefined

      const basePayload = {
        section_id: sectionId,
        combined_group_id: combinedGroupId,
        subject_id: form.subject_id,
        teacher_id: teacherId,
        room_id: form.room_id,
        reason: form.reason.trim() ? form.reason.trim() : null,
      }

      // Production-safe fallback: if slot is omitted, try teacher-window slots explicitly.
      if (!form.slot_id && teacherWindows.length > 0) {
        const candidates = slots
          .filter((slot) => {
            const day = Number(slot.day_of_week)
            const idx = Number(slot.slot_index)
            return teacherWindows.some((w) => {
              if (w.day_of_week !== null && Number(w.day_of_week) !== day) return false
              return idx >= Number(w.start_slot_index) && idx <= Number(w.end_slot_index)
            })
          })
          .sort((a, b) => (a.day_of_week - b.day_of_week) || (a.slot_index - b.slot_index))

        let saved = false
        let lastErr: any = null
        for (const slot of candidates) {
          try {
            await upsertSpecialAllotment({
              ...basePayload,
              slot_id: slot.id,
            })
            saved = true
            break
          } catch (e: any) {
            lastErr = e
          }
        }
        if (!saved) {
          throw (lastErr ?? new Error('No teacher-window slot could be saved. Please select slot manually.'))
        }
      } else {
        await upsertSpecialAllotment({
          ...basePayload,
          slot_id: form.slot_id || undefined,
        })
      }

      showToast('Saved special allotment')
      setForm((f) => ({ ...f, reason: '' }))
      await refreshTeacherData(teacherId)
    } catch (e: any) {
      showToast(`Save failed: ${String(e?.message ?? e)}`, 4000)
    } finally {
      setSaving(false)
    }
  }

  async function onDelete(entry: SpecialAllotment) {
    const ok = window.confirm('Delete this special allotment lock?')
    if (!ok) return
    setSaving(true)
    try {
      await deleteSpecialAllotment(entry.id, { cascade_combined: true })
      showToast('Deleted')
      await refreshTeacherData(teacherId)
    } catch (e: any) {
      showToast(`Delete failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setSaving(false)
    }
  }

  const activeEntries = React.useMemo(() => entries.filter((x) => x.is_active), [entries])

  const sectionById = React.useMemo(() => new Map(sections.map((s) => [s.id, s])), [sections])
  const subjectById = React.useMemo(() => new Map(subjects.map((s) => [s.id, s])), [subjects])

  const slotOptions = React.useMemo(
    () => slots.map((s) => ({ value: s.id, label: slotLabel(s) })),
    [slots],
  )

  const teacherOptions = React.useMemo(
    () =>
      teachers
        .slice()
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((t) => ({ value: t.id, label: `${t.code} — ${t.full_name}` })),
    [teachers],
  )

  const subjectSelectOptions = React.useMemo(() => {
    if (!teacherId) return [] as Array<{ value: string; label: string }>
    const fromAssignments = teacherSubjectRows
      .filter((r) => r.sections.some((s) => sectionById.has(s.section_id)))
      .map((r) => ({ id: r.subject_id, code: r.subject_code, name: r.subject_name }))

    const fromCombined = combinedGroups
      .filter((g) => g.teacher_id === teacherId)
      .map((g) => ({ id: g.subject_id, code: g.subject_code, name: g.subject_name }))

    const merged = new Map<string, { code: string; name: string }>()
    for (const item of [...fromAssignments, ...fromCombined]) {
      merged.set(item.id, { code: item.code, name: item.name })
    }
    return Array.from(merged.entries())
      .map(([id, item]) => ({ value: id, label: `${item.code} — ${item.name}` }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [teacherId, teacherSubjectRows, combinedGroups, sectionById])

  const targetOptions = React.useMemo(() => {
    if (!teacherId || !form.subject_id) return [] as Array<{ value: string; label: string }>

    const assignmentRow = teacherSubjectRows.find((r) => r.subject_id === form.subject_id)
    const sectionTargets = (assignmentRow?.sections ?? [])
      .filter((s) => sectionById.has(s.section_id))
      .map((s) => ({
        value: `S:${s.section_id}`,
        label: `Section: ${s.section_code} — ${s.section_name}`,
      }))

    const combinedTargets = combinedGroups
      .filter((g) => g.teacher_id === teacherId && g.subject_id === form.subject_id)
      .map((g) => {
        const label = (g.label ?? '').trim()
        const secCodes = g.sections.map((s) => s.section_code).join(', ')
        return {
          value: `C:${g.id}`,
          label: `Combined: ${label || `${g.subject_code} (${secCodes})`}`,
        }
      })

    return [...sectionTargets, ...combinedTargets]
  }, [teacherId, form.subject_id, teacherSubjectRows, combinedGroups, sectionById])

  const roomOptions = React.useMemo(() => {
    const subj = subjectById.get(form.subject_id) ?? null
    const isLab = String(subj?.subject_type ?? '').toUpperCase() === 'LAB'
    const specialRooms = rooms.filter((r) => Boolean((r as any).is_special))
    if (specialRooms.length === 0) return []
    if (!isLab) return specialRooms
    const labs = specialRooms.filter((r) => String((r as any).room_type ?? '').toUpperCase() === 'LAB')
    return labs.length ? labs : specialRooms
  }, [rooms, subjectById, form.subject_id])

  const roomSelectOptions = React.useMemo(
    () =>
      roomOptions
        .slice()
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((r) => ({ value: r.id, label: `${r.code} — ${r.name}` })),
    [roomOptions],
  )

  const displayEntries = React.useMemo(() => {
    const dedup = new Map<string, SpecialAllotment>()
    for (const e of activeEntries) {
      if (e.combined_group_id) {
        const key = `${e.combined_group_id}:${e.slot_id}:${e.subject_id}:${e.teacher_id}:${e.room_id}:${e.reason ?? ''}`
        if (!dedup.has(key)) dedup.set(key, e)
        continue
      }
      dedup.set(e.id, e)
    }
    return Array.from(dedup.values())
  }, [activeEntries])

  return (
    <div className="space-y-5">
      <Toast message={toast} />

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xl font-semibold text-slate-900">Special Allotments</div>
          <div className="mt-1 text-sm text-slate-600">
            Hard locked events applied before solving (teacher/room/section slot occupied).
          </div>
        </div>
        <button
          type="button"
          className="btn-secondary text-sm disabled:opacity-50"
          onClick={() => refreshBase()}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="text-xs font-medium text-slate-600" htmlFor="sa_teacher">
            Teacher
          </label>
          <PremiumSelect
            id="sa_teacher"
            ariaLabel="Teacher"
            className="mt-1"
            value={teacherId}
            onValueChange={(v) => {
              setTeacherId(v)
              setForm({ slot_id: '', subject_id: '', target_key: '', room_id: '', reason: '' })
            }}
            placeholder="Select teacher…"
            options={teacherOptions}
          />
        </div>

        <div className="rounded-xl border bg-slate-50 p-3 text-xs text-slate-600">
          <div>
            Program: <span className="font-semibold text-slate-800">{programCode}</span>
          </div>
          <div>
            Year: <span className="font-semibold text-slate-800">{academicYearNumber}</span>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border bg-white p-4">
        <div className="text-sm font-semibold text-slate-900">Create / Update Lock</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="sa_slot">
              Time slot (optional)
            </label>
            <PremiumSelect
              id="sa_slot"
              ariaLabel="Time slot"
              className="mt-1"
              value={form.slot_id}
              onValueChange={(v) => setForm((f) => ({ ...f, slot_id: v }))}
              placeholder="Select slot…"
              options={slotOptions}
              disabled={!teacherId}
            />
            <div className="mt-1 text-[11px] text-slate-500">Leave empty to auto-use teacher's normal timetable slot. If no history exists, select slot manually.</div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="sa_subject">
              Subject
            </label>
            <PremiumSelect
              id="sa_subject"
              ariaLabel="Subject"
              className="mt-1"
              value={form.subject_id}
              onValueChange={(v) => onSubjectChange(v)}
              placeholder="Select subject…"
              options={subjectSelectOptions}
              disabled={!teacherId}
            />
            <div className="mt-1 text-[11px] text-slate-500">Subjects are filtered by selected teacher assignments.</div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="sa_target">
              Section / Combined class
            </label>
            <PremiumSelect
              id="sa_target"
              ariaLabel="Section or combined class"
              className="mt-1"
              value={form.target_key}
              onValueChange={(v) => setForm((f) => ({ ...f, target_key: v }))}
              placeholder="Select target…"
              options={targetOptions}
              disabled={!teacherId || !form.subject_id}
            />
            <div className="mt-1 text-[11px] text-slate-500">Choose either one section or a full combined group.</div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="sa_room">
              Room
            </label>
            <PremiumSelect
              id="sa_room"
              ariaLabel="Room"
              className="mt-1"
              value={form.room_id}
              onValueChange={(v) => setForm((f) => ({ ...f, room_id: v }))}
              placeholder="Select room…"
              options={roomSelectOptions}
              disabled={!teacherId || !form.subject_id}
            />
            <div className="mt-1 text-[11px] text-slate-500">
              Only special rooms are shown. Mark rooms as special in Rooms.
            </div>
          </div>

          <div className="md:col-span-2">
            <label className="text-xs font-medium text-slate-600" htmlFor="sa_reason">
              Reason (optional)
            </label>
            <input
              id="sa_reason"
              className="input-premium mt-1 w-full text-sm"
              value={form.reason}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
              placeholder="e.g., Guest lecture / Exam / Lab maintenance"
              disabled={!teacherId}
            />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2">
          <button
            type="button"
            className="btn-primary text-sm disabled:opacity-50"
            onClick={() => onSave()}
            disabled={saving || loading}
          >
            Save Lock
          </button>
          <div className="text-xs text-slate-500">
            Errors like <span className="font-mono">SPECIAL_ALLOTMENT_TEACHER_SLOT_CONFLICT</span> mean a clash.
          </div>
        </div>
      </div>

      <div className="rounded-2xl border bg-white p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="text-sm font-semibold text-slate-900">Current Locks</div>
          <div className="text-xs text-slate-500">{displayEntries.length} active</div>
        </div>

        {!teacherId ? (
          <div className="mt-3 text-sm text-slate-600">Select a teacher to view locks.</div>
        ) : displayEntries.length === 0 ? (
          <div className="mt-3 text-sm text-slate-600">No special allotments for this teacher.</div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-slate-500">
                  <th className="py-2 pr-4">Slot</th>
                  <th className="py-2 pr-4">Target</th>
                  <th className="py-2 pr-4">Subject</th>
                  <th className="py-2 pr-4">Teacher</th>
                  <th className="py-2 pr-4">Room</th>
                  <th className="py-2 pr-4">Reason</th>
                  <th className="py-2 pr-0"></th>
                </tr>
              </thead>
              <tbody>
                {displayEntries.map((e) => (
                  <tr key={e.id} className="border-b last:border-b-0">
                    <td className="py-2 pr-4 whitespace-nowrap">
                      {WEEKDAYS[e.day_of_week] ?? `D${e.day_of_week}`} #{e.slot_index} ({e.start_time}-{e.end_time})
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">{e.target_label || e.section_code}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">
                      <span className="font-semibold">🔒 {e.subject_code}</span>{' '}
                      <span className="text-xs text-slate-500">({e.subject_type})</span>
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">{e.teacher_code}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">{e.room_code}</td>
                    <td className="py-2 pr-4 text-slate-600">{e.reason || '—'}</td>
                    <td className="py-2 pr-0 text-right">
                      <button
                        type="button"
                        className="btn-danger text-xs disabled:opacity-50"
                        onClick={() => onDelete(e)}
                        disabled={saving}
                      >
                        Delete
                      </button>
                    </td>
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
