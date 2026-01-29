import * as React from 'react'

/**
 * Locks scrolling in app scroll regions while a modal is open.
 *
 * Note: body/html scrolling is already disabled by layout CSS, but the app uses
 * internal scroll regions (sidebar + main). This hook prevents those from
 * scrolling behind an open modal.
 */
export function useModalScrollLock(isOpen: boolean) {
  React.useEffect(() => {
    if (!isOpen) return

    const body = document.body
    const html = document.documentElement

    // Preserve prior inline styles so we can restore them safely.
    const prevBodyOverflow = body.style.overflow
    const prevHtmlOverflow = html.style.overflow

    body.dataset.modalOpen = 'true'
    body.style.overflow = 'hidden'
    html.style.overflow = 'hidden'

    return () => {
      delete body.dataset.modalOpen
      body.style.overflow = prevBodyOverflow
      html.style.overflow = prevHtmlOverflow
    }
  }, [isOpen])
}
