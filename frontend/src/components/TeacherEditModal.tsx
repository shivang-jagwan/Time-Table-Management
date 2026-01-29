import React from 'react'
import type { Teacher, TeacherPut } from '../api/teachers'
import { useModalScrollLock } from '../hooks/useModalScrollLock'
import { PremiumSelect } from './PremiumSelect'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export type TeacherEditModalProps = {
  open: boolean
  teacher: Teacher | null
  loading?: boolean
  onClose: () => void
  onSave: (payload: TeacherPut) => Promise<void> | void
}

type FormState = {
  full_name: string
  weekly_off_day: string
  max_per_day: number
  max_per_week: number
  max_continuous: number
  is_active: boolean
}

function teacherToForm(t: Teacher): FormState {
  return {
    full_name: t.full_name ?? '',
    weekly_off_day: t.weekly_off_day == null ? '' : String(t.weekly_off_day),
    max_per_day: Number(t.max_per_day ?? 0),
    max_per_week: Number(t.max_per_week ?? 0),
    max_continuous: Number(t.max_continuous ?? 1),
    is_active: Boolean(t.is_active),
  }
}

function validateForm(f: FormState): string[] {
  const errors: string[] = []
  if (!f.full_name.trim()) errors.push('Full name is required')

  if (Number.isNaN(f.max_per_day) || f.max_per_day < 0) errors.push('Max per day must be >= 0')
  if (Number.isNaN(f.max_per_week) || f.max_per_week < 0) errors.push('Max per week must be >= 0')
  if (Number.isNaN(f.max_continuous) || f.max_continuous < 1)
    errors.push('Max continuous must be >= 1')

  if (f.max_per_day > 6) errors.push('Max per day cannot exceed 6')
  if (f.max_per_week > 30) errors.push('Max per week cannot exceed 30')

  if (f.max_per_day > f.max_per_week) errors.push('Max per day must be <= Max per week')
  if (f.max_continuous > f.max_per_day) errors.push('Max continuous must be <= Max per day')

  if (f.max_per_day * 6 < f.max_per_week) {
    errors.push('Max per week is too high for Max per day across 6 days')
  }

  const off = f.weekly_off_day === '' ? null : Number(f.weekly_off_day)
  if (off != null && (Number.isNaN(off) || off < 0 || off > 5)) {
    errors.push('Weekly Leave must be Mon–Sat or None')
  }

  return errors
}

export function TeacherEditModal({
  open,
  teacher,
  loading,
  onClose,
  onSave,
}: TeacherEditModalProps) {
  useModalScrollLock(open)

  const [form, setForm] = React.useState<FormState | null>(null)
  const [errors, setErrors] = React.useState<string[]>([])

  React.useEffect(() => {
    if (!open || !teacher) {
      setForm(null)
      setErrors([])
      return
    }
    setForm(teacherToForm(teacher))
    setErrors([])
  }, [open, teacher])

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    if (open) window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open || !teacher || !form) return null

  const idPrefix = `edit_teacher_${teacher.id}`

  async function handleSave() {
    if (!form) return
    const currentForm = form

    const nextErrors = validateForm(currentForm)
    setErrors(nextErrors)
    if (nextErrors.length) return

    const payload: TeacherPut = {
      full_name: currentForm.full_name.trim(),
      weekly_off_day: currentForm.weekly_off_day === '' ? null : Number(currentForm.weekly_off_day),
      max_per_day: Number(currentForm.max_per_day),
      max_per_week: Number(currentForm.max_per_week),
      max_continuous: Number(currentForm.max_continuous),
      is_active: Boolean(currentForm.is_active),
    }

    await onSave(payload)
  }

  return (
    <div
      className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-[600px] bg-white/80 backdrop-blur-lg rounded-2xl shadow-2xl p-6 border border-white/40 animate-scaleIn"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-lg font-semibold text-slate-900">Edit Teacher</div>
            <div className="mt-1 text-xs text-slate-500">Update constraints used by the solver.</div>
          </div>
          <button
            className="btn-secondary text-xs font-medium text-slate-800 disabled:opacity-50"
            onClick={onClose}
            disabled={Boolean(loading)}
            type="button"
          >
            Close
          </button>
        </div>

          <div className="mt-4 grid gap-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label htmlFor={`${idPrefix}_code`} className="text-xs font-medium text-slate-600">
                  Code
                </label>
                <input
                  id={`${idPrefix}_code`}
                  className="input-premium mt-1 w-full text-sm bg-slate-50 text-slate-700"
                  value={teacher.code}
                  disabled
                />
              </div>
              <div>
                <label htmlFor={`${idPrefix}_full_name`} className="text-xs font-medium text-slate-600">
                  Full name (required)
                </label>
                <input
                  id={`${idPrefix}_full_name`}
                  className="input-premium mt-1 w-full text-sm"
                  value={form.full_name}
                  onChange={(e) => setForm((f) => (f ? { ...f, full_name: e.target.value } : f))}
                  autoComplete="off"
                />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label htmlFor={`${idPrefix}_weekly_leave`} className="text-xs font-medium text-slate-600">
                  Weekly Leave (optional)
                </label>
                <div className="mt-1 text-[11px] text-slate-500">Teacher will not be scheduled on this day.</div>
                <PremiumSelect
                  id={`${idPrefix}_weekly_leave`}
                  ariaLabel="Weekly leave"
                  className="mt-2 text-sm"
                  value={form.weekly_off_day || '__none__'}
                  onValueChange={(v) => setForm((f) => (f ? { ...f, weekly_off_day: v === '__none__' ? '' : v } : f))}
                  options={[
                    { value: '__none__', label: 'None' },
                    ...WEEKDAYS.map((d, i) => ({ value: String(i), label: d })),
                  ]}
                />
              </div>

              <div>
                <label htmlFor={`${idPrefix}_max_cont`} className="text-xs font-medium text-slate-600">
                  Max continuous
                </label>
                <input
                  id={`${idPrefix}_max_cont`}
                  type="number"
                  className="input-premium mt-1 w-full text-sm"
                  value={form.max_continuous}
                  onChange={(e) =>
                    setForm((f) => (f ? { ...f, max_continuous: Number(e.target.value) } : f))
                  }
                  min={1}
                />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label htmlFor={`${idPrefix}_max_day`} className="text-xs font-medium text-slate-600">
                  Max per day
                </label>
                <input
                  id={`${idPrefix}_max_day`}
                  type="number"
                  className="input-premium mt-1 w-full text-sm"
                  value={form.max_per_day}
                  onChange={(e) => setForm((f) => (f ? { ...f, max_per_day: Number(e.target.value) } : f))}
                  min={0}
                  max={6}
                />
              </div>
              <div>
                <label htmlFor={`${idPrefix}_max_week`} className="text-xs font-medium text-slate-600">
                  Max per week
                </label>
                <input
                  id={`${idPrefix}_max_week`}
                  type="number"
                  className="input-premium mt-1 w-full text-sm"
                  value={form.max_per_week}
                  onChange={(e) => setForm((f) => (f ? { ...f, max_per_week: Number(e.target.value) } : f))}
                  min={0}
                  max={30}
                />
              </div>
            </div>

            <label className="checkbox-row rounded-lg border border-white/40 bg-white/70">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => (f ? { ...f, is_active: e.target.checked } : f))}
              />
              <span className="text-slate-700 font-medium">Active</span>
            </label>

            {errors.length > 0 && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <div className="text-xs font-semibold">Please fix:</div>
                <ul className="mt-1 list-disc pl-5 text-xs">
                  {errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-1 flex items-center justify-end gap-2">
              <button
                className="btn-secondary text-sm font-medium text-slate-800 disabled:opacity-50"
                onClick={onClose}
                disabled={Boolean(loading)}
                type="button"
              >
                Cancel
              </button>
              <button
                className="btn-primary text-sm font-semibold disabled:opacity-50"
                onClick={handleSave}
                disabled={Boolean(loading)}
                type="button"
              >
                {loading ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </div>
      </div>
    </div>
  )
}
