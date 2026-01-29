export function Placeholder({ title }: { title: string }) {
  return (
    <div className="rounded-3xl border bg-white p-6">
      <div className="text-lg font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-sm text-slate-600">
        This module will be implemented after the Login + Layout confirmation.
      </div>
    </div>
  )
}
