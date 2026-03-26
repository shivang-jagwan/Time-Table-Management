import React from 'react'

// Legacy page retained to avoid breaking imports.
// The production app uses routing via main.tsx + Layout.
export function App() {
  return (
    <div className="min-h-dvh grid place-items-center bg-gray-50">
      <div className="rounded-xl border bg-white p-6 text-sm text-gray-700">
        This page is deprecated. Use the main application routes.
      </div>
    </div>
  )
}
