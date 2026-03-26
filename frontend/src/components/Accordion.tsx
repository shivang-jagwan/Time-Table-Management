import React from 'react'

export function Accordion({
  title,
  children,
  defaultOpen = false,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = React.useState(defaultOpen)
  return (
    <div className="rounded-2xl border bg-white">
      <button
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
        type="button"
      >
        <span className="text-sm font-semibold text-slate-900">{title}</span>
        <span className="text-slate-500">{open ? '−' : '+'}</span>
      </button>
      {open ? <div className="border-t p-4">{children}</div> : null}
    </div>
  )
}
