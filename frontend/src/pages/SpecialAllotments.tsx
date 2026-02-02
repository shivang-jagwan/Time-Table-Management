import React from 'react'
import { useLayoutContext } from '../components/Layout'
import { Toast } from '../components/Toast'
import { PremiumSelect } from '../components/PremiumSelect'
import { listSections, type Section } from '../api/sections'
import { listRooms, type Room } from '../api/rooms'
import { listTeachers, type Teacher } from '../api/teachers'
import {
  listTimeSlots,
  listSectionRequiredSubjects,
  getAssignedTeacher,
  listSpecialAllotments,
  upsertSpecialAllotment,
  deleteSpecialAllotment,
  type TimeSlot,
  type RequiredSubject,
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
  const [sectionId, setSectionId] = React.useState('')

  const [slots, setSlots] = React.useState<TimeSlot[]>([])
  const [subjects, setSubjects] = React.useState<RequiredSubject[]>([])
  const [rooms, setRooms] = React.useState<Room[]>([])
  const [teachers, setTeachers] = React.useState<Teacher[]>([])

  const [entries, setEntries] = React.useState<SpecialAllotment[]>([])

  const [saving, setSaving] = React.useState(false)
  const [form, setForm] = React.useState<{ slot_id: string; subject_id: string; teacher_id: string; room_id: string; reason: string }>(
    { slot_id: '', subject_id: '', teacher_id: '', room_id: '', reason: '' },
  )

  function showToast(message: string, ms = 2500) {
    setToast(message)
    window.setTimeout(() => setToast(''), ms)
  }

  async function refreshBase() {
    setLoading(true)
    try {
      const shouldLoadSections = Boolean(programCode) && Boolean(academicYearNumber)
      const [sec, ts, r, t] = await Promise.all([
        shouldLoadSections
          ? listSections({ program_code: programCode, academic_year_number: academicYearNumber })
          : Promise.resolve([]),
        listTimeSlots(),
        listRooms(),
        listTeachers(),
      ])
      if (!shouldLoadSections) {
        setSections([])
        showToast('Select program + year first (top bar)', 3500)
      } else {
        setSections(sec.filter((x) => Boolean(x.is_active)))
      }
      setSlots(ts)
      setRooms(r.filter((x) => Boolean(x.is_active)))
      setTeachers(t.filter((x) => Boolean(x.is_active)))
    } catch (e: any) {
      showToast(`Load failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setLoading(false)
    }
  }

  async function refreshSectionData(selectedSectionId: string) {
    if (!selectedSectionId) {
      setSubjects([])
      setEntries([])
      return
    }
    setLoading(true)
    try {
      const [subj, sa] = await Promise.all([
        listSectionRequiredSubjects({ section_id: selectedSectionId }),
        listSpecialAllotments({ section_id: selectedSectionId }),
      ])
      setSubjects(subj.filter((s) => Boolean(s.is_active)))
      setEntries(sa)
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
    refreshSectionData(sectionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId])

  async function onSubjectChange(subjectId: string) {
    setForm((f) => ({ ...f, subject_id: subjectId, teacher_id: '' }))
    if (!sectionId || !subjectId) return
    try {
      const assigned = await getAssignedTeacher({ section_id: sectionId, subject_id: subjectId })
      setForm((f) => ({ ...f, teacher_id: assigned.teacher_id }))
    } catch {
      showToast('No assigned teacher for this subject/section', 3500)
    }
  }

  async function onSave() {
    if (!sectionId) {
      showToast('Pick a section', 2500)
      return
    }
    if (!form.slot_id || !form.subject_id || !form.room_id) {
      showToast('Pick slot, subject, and room', 2500)
      return
    }
    if (!form.teacher_id) {
      showToast('Pick a teacher (must match strict assignment)', 3000)
      return
    }

    setSaving(true)
    try {
      await upsertSpecialAllotment({
        section_id: sectionId,
        slot_id: form.slot_id,
        subject_id: form.subject_id,
        teacher_id: form.teacher_id,
        room_id: form.room_id,
        reason: form.reason.trim() ? form.reason.trim() : null,
      })
      showToast('Saved special allotment')
      setForm((f) => ({ ...f, reason: '' }))
      await refreshSectionData(sectionId)
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
      await deleteSpecialAllotment(entry.id)
      showToast('Deleted')
      await refreshSectionData(sectionId)
    } catch (e: any) {
      showToast(`Delete failed: ${String(e?.message ?? e)}`, 3500)
    } finally {
      setSaving(false)
    }
  }

  const activeEntries = React.useMemo(() => entries.filter((x) => x.is_active), [entries])

  const sectionOptions = React.useMemo(
    () =>
      sections
        .slice()
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((s) => ({ value: s.id, label: `${s.code} — ${s.name}` })),
    [sections],
  )

  const slotOptions = React.useMemo(
    () => slots.map((s) => ({ value: s.id, label: slotLabel(s) })),
    [slots],
  )

  const subjectOptions = React.useMemo(
    () =>
      subjects
        .slice()
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((s) => ({ value: s.id, label: `${s.code} — ${s.name}` })),
    [subjects],
  )

  const teacherOptions = React.useMemo(
    () =>
      teachers
        .slice()
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((t) => ({ value: t.id, label: `${t.code} — ${t.full_name}` })),
    [teachers],
  )

  const roomOptions = React.useMemo(() => {
    const subj = subjects.find((s) => s.id === form.subject_id) ?? null
    const isLab = String(subj?.subject_type ?? '').toUpperCase() === 'LAB'
    const specialRooms = rooms.filter((r) => Boolean((r as any).is_special))
    if (specialRooms.length === 0) return []
    if (!isLab) return specialRooms
    const labs = specialRooms.filter((r) => String((r as any).room_type ?? '').toUpperCase() === 'LAB')
    return labs.length ? labs : specialRooms
  }, [rooms, subjects, form.subject_id])

  const roomSelectOptions = React.useMemo(
    () =>
      roomOptions
        .slice()
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((r) => ({ value: r.id, label: `${r.code} — ${r.name}` })),
    [roomOptions],
  )

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
          <label className="text-xs font-medium text-slate-600" htmlFor="sa_section">
            Section
          </label>
          <PremiumSelect
            id="sa_section"
            ariaLabel="Section"
            className="mt-1"
            value={sectionId}
            onValueChange={(v) => setSectionId(v)}
            placeholder="Select section…"
            options={sectionOptions}
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
              Time slot
            </label>
            <PremiumSelect
              id="sa_slot"
              ariaLabel="Time slot"
              className="mt-1"
              value={form.slot_id}
              onValueChange={(v) => setForm((f) => ({ ...f, slot_id: v }))}
              placeholder="Select slot…"
              options={slotOptions}
              disabled={!sectionId}
            />
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
              options={subjectOptions}
              disabled={!sectionId}
            />
            <div className="mt-1 text-[11px] text-slate-500">Teacher must match strict assignment.</div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600" htmlFor="sa_teacher">
              Teacher
            </label>
            <PremiumSelect
              id="sa_teacher"
              ariaLabel="Teacher"
              className="mt-1"
              value={form.teacher_id}
              onValueChange={(v) => setForm((f) => ({ ...f, teacher_id: v }))}
              placeholder="Select teacher…"
              options={teacherOptions}
              disabled={!sectionId || !form.subject_id}
            />
            <div className="mt-1 text-[11px] text-slate-500">Auto-fills when a strict assignment exists.</div>
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
              disabled={!sectionId || !form.subject_id}
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
              disabled={!sectionId}
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
          <div className="text-xs text-slate-500">{activeEntries.length} active</div>
        </div>

        {!sectionId ? (
          <div className="mt-3 text-sm text-slate-600">Select a section to view locks.</div>
        ) : activeEntries.length === 0 ? (
          <div className="mt-3 text-sm text-slate-600">No special allotments for this section.</div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-slate-500">
                  <th className="py-2 pr-4">Slot</th>
                  <th className="py-2 pr-4">Subject</th>
                  <th className="py-2 pr-4">Teacher</th>
                  <th className="py-2 pr-4">Room</th>
                  <th className="py-2 pr-4">Reason</th>
                  <th className="py-2 pr-0"></th>
                </tr>
              </thead>
              <tbody>
                {activeEntries.map((e) => (
                  <tr key={e.id} className="border-b last:border-b-0">
                    <td className="py-2 pr-4 whitespace-nowrap">
                      {WEEKDAYS[e.day_of_week] ?? `D${e.day_of_week}`} #{e.slot_index} ({e.start_time}-{e.end_time})
                    </td>
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
