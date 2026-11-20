import { createContext, useContext } from 'react'

export type ConfirmOptions = {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  /** "danger" styles the confirm button for destructive actions (delete). */
  tone?: 'default' | 'danger'
  /** If set, the user must type this exact text before confirming (e.g. their email). */
  requireText?: string
}

export type ToastKind = 'success' | 'info' | 'error'

export type UIContextValue = {
  /** Styled replacement for window.confirm(); resolves true when confirmed. */
  confirm: (opts: ConfirmOptions) => Promise<boolean>
  /** Small notification in the corner that disappears on its own. */
  toast: (message: string, kind?: ToastKind) => void
}

export const UIContext = createContext<UIContextValue | null>(null)

export function useUI(): UIContextValue {
  const ctx = useContext(UIContext)
  if (!ctx) throw new Error('useUI must be used inside <UIProvider>')
  return ctx
}
