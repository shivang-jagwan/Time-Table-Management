import React from 'react'
import type { Section, SectionStrengthPut } from '../api/sections'
import { useModalScrollLock } from '../hooks/useModalScrollLock'

export type SectionStrengthEditModalProps = {
  open: boolean
  section: Section | null
  loading?: boolean
  onClose: () => void
  onSave: (payload: SectionStrengthPut) => Promise<void> | void
}

type FormState = {
  strength: number
}

function sectionToForm(s: Section): FormState {
  return { strength: Number(s.strength ?? 0) }
}

function validateForm(f: FormState): string[] {
  const errors: string[] = []
  if (Number.isNaN(f.strength) || f.strength < 0) errors.push('Strength must be >= 0')
  return errors
}

export function SectionStrengthEditModal({
  open,
  section,
  loading,
  onClose,
  onSave,
}: SectionStrengthEditModalProps) {
  useModalScrollLock(open)

  const [form, setForm] = React.useState<FormState | null>(null)
  const [errors, setErrors] = React.useState<string[]>([])

  React.useEffect(() => {
    if (!open || !section) {
      setForm(null)
      setErrors([])
      return
    }
    setForm(sectionToForm(section))
    setErrors([])
  }, [open, section])

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    if (open) window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open || !section || !form) return null

  const idPrefix = `edit_section_strength_${section.id}`
  const dirty = Number(form.strength) !== Number(section.strength)

  async function handleSave() {
    if (!form) return

    const nextErrors = validateForm(form)
    setErrors(nextErrors)
    if (nextErrors.length) return

    const payload: SectionStrengthPut = { strength: Number(form.strength) }
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
            <div className="text-lg font-semibold text-slate-900">Edit Strength</div>
            <div className="mt-1 text-xs text-slate-500">
              {section.code} — {section.name}
            </div>
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
            <div>
              <label htmlFor={`${idPrefix}_strength`} className="text-xs font-medium text-slate-600">
                Strength
              </label>
              <input
                id={`${idPrefix}_strength`}
                type="number"
                min={0}
                className="input-premium mt-1 w-full text-sm"
                value={form.strength}
                onChange={(e) => setForm((f) => (f ? { ...f, strength: Number(e.target.value) } : f))}
              />
              <div className="mt-1 text-[11px] text-slate-500">Used for room capacity decisions in future solves.</div>
            </div>

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
