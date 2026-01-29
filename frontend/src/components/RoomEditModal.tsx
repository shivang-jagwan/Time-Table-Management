import React from 'react'
import type { Room, RoomPut } from '../api/rooms'
import { useModalScrollLock } from '../hooks/useModalScrollLock'
import { PremiumSelect } from './PremiumSelect'

export type RoomEditModalProps = {
  open: boolean
  room: Room | null
  loading?: boolean
  onClose: () => void
  onSave: (payload: RoomPut) => Promise<void> | void
}

const ROOM_TYPES = [
  { label: 'Classroom', value: 'CLASSROOM' },
  { label: 'Lecture Theatre', value: 'LT' },
  { label: 'Lab', value: 'LAB' },
]

type FormState = {
  code: string
  name: string
  room_type: string
  capacity: number
  is_active: boolean
}

function roomToForm(r: Room): FormState {
  return {
    code: r.code ?? '',
    name: r.name ?? '',
    room_type: r.room_type ?? 'CLASSROOM',
    capacity: Number(r.capacity ?? 0),
    is_active: Boolean(r.is_active),
  }
}

function validateForm(f: FormState): string[] {
  const errors: string[] = []
  if (!f.code.trim()) errors.push('Code is required')
  if (!f.name.trim()) errors.push('Name is required')
  if (Number.isNaN(f.capacity) || f.capacity < 0) errors.push('Capacity must be >= 0')
  if (!String(f.room_type).trim()) errors.push('Type is required')
  return errors
}

export function RoomEditModal({ open, room, loading, onClose, onSave }: RoomEditModalProps) {
  useModalScrollLock(open)

  const [form, setForm] = React.useState<FormState | null>(null)
  const [errors, setErrors] = React.useState<string[]>([])

  React.useEffect(() => {
    if (!open || !room) {
      setForm(null)
      setErrors([])
      return
    }
    setForm(roomToForm(room))
    setErrors([])
  }, [open, room])

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    if (open) window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open || !room || !form) return null

  const idPrefix = `edit_room_${room.id}`

  const dirty =
    form.code.trim() !== (room.code ?? '').trim() ||
    form.name.trim() !== (room.name ?? '').trim() ||
    String(form.room_type) !== String(room.room_type) ||
    Number(form.capacity) !== Number(room.capacity) ||
    Boolean(form.is_active) !== Boolean(room.is_active)

  async function handleSave() {
    if (!form) return

    const nextErrors = validateForm(form)
    setErrors(nextErrors)
    if (nextErrors.length) return

    const payload: RoomPut = {
      code: form.code.trim(),
      name: form.name.trim(),
      room_type: form.room_type,
      capacity: Number(form.capacity),
      is_active: Boolean(form.is_active),
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
            <div className="text-lg font-semibold text-slate-900">Edit Room</div>
            <div className="mt-1 text-xs text-slate-500">Changes apply to future solves.</div>
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
                  className="input-premium mt-1 w-full text-sm"
                  value={form.code}
                  onChange={(e) => setForm((f) => (f ? { ...f, code: e.target.value } : f))}
                  autoComplete="off"
                />
              </div>
              <div>
                <label htmlFor={`${idPrefix}_type`} className="text-xs font-medium text-slate-600">
                  Type
                </label>
                <PremiumSelect
                  id={`${idPrefix}_type`}
                  ariaLabel="Room type"
                  className="mt-1 text-sm"
                  value={form.room_type}
                  onValueChange={(v) => setForm((f) => (f ? { ...f, room_type: v } : f))}
                  options={ROOM_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                />
              </div>
            </div>

            <div>
              <label htmlFor={`${idPrefix}_name`} className="text-xs font-medium text-slate-600">
                Name
              </label>
              <input
                id={`${idPrefix}_name`}
                className="input-premium mt-1 w-full text-sm"
                value={form.name}
                onChange={(e) => setForm((f) => (f ? { ...f, name: e.target.value } : f))}
                autoComplete="off"
              />
            </div>

            <div>
              <label htmlFor={`${idPrefix}_cap`} className="text-xs font-medium text-slate-600">
                Capacity
              </label>
              <input
                id={`${idPrefix}_cap`}
                type="number"
                min={0}
                className="input-premium mt-1 w-full text-sm"
                value={form.capacity}
                onChange={(e) => setForm((f) => (f ? { ...f, capacity: Number(e.target.value) } : f))}
              />
            </div>

            <label className="checkbox-row rounded-lg border border-white/40 bg-white/70">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => (f ? { ...f, is_active: e.target.checked } : f))}
              />
              <span className="text-slate-700 font-medium">Active</span>
            </label>

            {errors.length ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <ul className="list-disc pl-5">
                  {errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            ) : null}

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
                disabled={Boolean(loading) || !dirty}
                title={dirty ? '' : 'No changes to save'}
                type="button"
              >
                {loading ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
      </div>
    </div>
  )
}
