import React from 'react'

type Props = {
  open: boolean
  onClick: () => void
  label?: string
  className?: string
}

export function HamburgerButton({ open, onClick, label = 'Toggle Sidebar', className }: Props) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={
        [
          'group relative grid h-10 w-10 place-items-center rounded-md transition',
          'focus:outline-none focus:ring-2',
          className ?? 'text-gray-700 hover:bg-gray-100 focus:ring-indigo-500/40',
        ].join(' ')
      }
    >
      <span className="relative block h-5 w-6" aria-hidden="true">
        <span
          className={
            'absolute left-0 top-0 h-0.5 w-6 rounded-full bg-current transition-all duration-300 ' +
            (open ? 'top-2.5 rotate-45' : 'rotate-0')
          }
        />
        <span
          className={
            'absolute left-0 top-2.5 h-0.5 w-6 rounded-full bg-current transition-all duration-300 ' +
            (open ? 'opacity-0' : 'opacity-100')
          }
        />
        <span
          className={
            'absolute left-0 top-5 h-0.5 w-6 rounded-full bg-current transition-all duration-300 ' +
            (open ? 'top-2.5 -rotate-45' : 'rotate-0')
          }
        />
      </span>
    </button>
  )
}
