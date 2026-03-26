import React from 'react'

export function Toast({ message }: { message: string }) {
  if (!message) return null
  return (
    <div className="fixed bottom-4 right-4 rounded-xl border border-white/20 bg-white/80 px-4 py-3 shadow-lg backdrop-blur-[10px]">
      <div className="text-sm text-slate-800">{message}</div>
    </div>
  )
}
