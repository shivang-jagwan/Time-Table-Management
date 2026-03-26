import React from 'react'
import { createTeacher, deleteTeacher, listTeachers, Teacher } from '../api/teachers'
import { PremiumSelect } from '../components/PremiumSelect'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function TeacherManagement({ onToast }: { onToast: (msg: string) => void }) {
  const [items, setItems] = React.useState<Teacher[]>([])
  const [loading, setLoading] = React.useState(false)

  const [form, setForm] = React.useState({
    code: '',
    full_name: '',
    weekly_off_day: '',
    max_per_day: 4,
    max_per_week: 20,
    max_continuous: 3,
    is_active: true,
  })

  async function refresh() {
    setLoading(true)
    try {
      const data = await listTeachers()
      setItems(data)
    } catch (e: any) {
      onToast(`Load failed: ${String(e?.message ?? e)}`)
    } finally {
      setLoading(false)
      setTimeout(() => onToast(''), 2500)
    }
  }

  React.useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function onCreate() {
    setLoading(true)
    try {
      await createTeacher({
        code: form.code.trim(),
        full_name: form.full_name.trim(),
        weekly_off_day: form.weekly_off_day === '' ? null : Number(form.weekly_off_day),
        max_per_day: Number(form.max_per_day),
        max_per_week: Number(form.max_per_week),
        max_continuous: Number(form.max_continuous),
        is_active: Boolean(form.is_active),
      })
      onToast('Teacher saved')
      setForm((f) => ({ ...f, code: '', full_name: '' }))
      await refresh()
    } catch (e: any) {
      onToast(`Save failed: ${String(e?.message ?? e)}`)
    } finally {
      setLoading(false)
      setTimeout(() => onToast(''), 2500)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Delete this teacher?')) return
    setLoading(true)
    try {
      await deleteTeacher(id)
      onToast('Teacher deleted')
      await refresh()
    } catch (e: any) {
      onToast(`Delete failed: ${String(e?.message ?? e)}`)
    } finally {
      setLoading(false)
      setTimeout(() => onToast(''), 2500)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label htmlFor="tm_code" className="text-xs font-medium text-slate-600">
            Code
          </label>
          <input
            id="tm_code"
            className="input-premium mt-1 w-full text-sm"
            value={form.code}
            onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
            placeholder="TCH001"
          />
        </div>
        <div>
          <label htmlFor="tm_full_name" className="text-xs font-medium text-slate-600">
            Full name
          </label>
          <input
            id="tm_full_name"
            className="input-premium mt-1 w-full text-sm"
            value={form.full_name}
            onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
            placeholder="Dr. A. Kumar"
          />
        </div>
        <div>
          <label htmlFor="tm_weekly_leave" className="text-xs font-medium text-slate-600">
            Weekly Leave (optional)
          </label>
          <PremiumSelect
            id="tm_weekly_leave"
            ariaLabel="Weekly leave"
            className="mt-1 text-sm"
            value={form.weekly_off_day || '__none__'}
            onValueChange={(v) => setForm((f) => ({ ...f, weekly_off_day: v === '__none__' ? '' : v }))}
            options={[
              { value: '__none__', label: 'None' },
              ...WEEKDAYS.map((d, i) => ({ value: String(i), label: d })),
            ]}
          />
        </div>
        <div>
          <label htmlFor="tm_max_cont" className="text-xs font-medium text-slate-600">
            Max continuous
          </label>
          <input
            id="tm_max_cont"
            type="number"
            className="input-premium mt-1 w-full text-sm"
            value={form.max_continuous}
            onChange={(e) => setForm((f) => ({ ...f, max_continuous: Number(e.target.value) }))}
            min={1}
          />
        </div>
        <div>
          <label htmlFor="tm_max_day" className="text-xs font-medium text-slate-600">
            Max/day
          </label>
          <input
            id="tm_max_day"
            type="number"
            className="input-premium mt-1 w-full text-sm"
            value={form.max_per_day}
            onChange={(e) => setForm((f) => ({ ...f, max_per_day: Number(e.target.value) }))}
            min={0}
          />
        </div>
        <div>
          <label htmlFor="tm_max_week" className="text-xs font-medium text-slate-600">
            Max/week
          </label>
          <input
            id="tm_max_week"
            type="number"
            className="input-premium mt-1 w-full text-sm"
            value={form.max_per_week}
            onChange={(e) => setForm((f) => ({ ...f, max_per_week: Number(e.target.value) }))}
            min={0}
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          className="btn-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          onClick={onCreate}
          disabled={loading || !form.code.trim() || !form.full_name.trim()}
        >
          {loading ? 'Saving…' : 'Save Teacher'}
        </button>
        <button
          className="btn-secondary px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-50"
          onClick={refresh}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div className="rounded-2xl border bg-slate-50">
        <div className="flex items-center justify-between border-b px-4 py-2">
          <div className="text-xs font-semibold text-slate-700">Teachers</div>
          <div className="text-xs text-slate-500">{items.length} total</div>
        </div>
        <div className="max-h-72 overflow-auto p-2">
          {items.length === 0 ? (
            <div className="p-4 text-sm text-slate-600">No teachers yet.</div>
          ) : (
            <div className="space-y-2">
              {items.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between rounded-xl border bg-white px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-900">
                      {t.full_name}
                    </div>
                    <div className="text-xs text-slate-500">
                      {t.code} • off: {t.weekly_off_day == null ? 'None' : WEEKDAYS[t.weekly_off_day]}
                    </div>
                  </div>
                  <button
                    className="btn-danger px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
                    onClick={() => onDelete(t.id)}
                    disabled={loading}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
