import React from 'react'

export function SummaryCard({
  title,
  value,
  subtitle,
}: {
  title: string
  value: React.ReactNode
  subtitle?: string
}) {
  return (
    <div className="rounded-2xl border bg-white p-4 shadow-sm">
      <div className="text-xs font-medium text-slate-500">{title}</div>
      <div className="mt-2 text-2xl font-semibold text-slate-900">{value}</div>
      {subtitle ? <div className="mt-1 text-xs text-slate-500">{subtitle}</div> : null}
    </div>
  )
}
