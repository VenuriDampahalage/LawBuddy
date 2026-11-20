import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { type ConfirmOptions, type ToastKind, UIContext } from '../lib/ui'

type Toast = { id: number; message: string; kind: ToastKind }
type PendingConfirm = ConfirmOptions & { resolve: (ok: boolean) => void }

const TOAST_MS = 4000
let nextId = 1

/** Provides confirm() dialogs and toast notifications to the whole app. */
export default function UIProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const confirm = useCallback(
    (opts: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...opts, resolve })),
    [],
  )

  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), [])
  const toast = useCallback(
    (message: string, kind: ToastKind = 'success') => {
      const id = nextId++
      setToasts((ts) => [...ts.slice(-3), { id, message, kind }])
      window.setTimeout(() => dismiss(id), kind === 'error' ? TOAST_MS * 1.5 : TOAST_MS)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ confirm, toast }), [confirm, toast])

  const close = (ok: boolean) => {
    pending?.resolve(ok)
    setPending(null)
  }

  return (
    <UIContext.Provider value={value}>
      {children}
      {pending && <ConfirmDialog opts={pending} onClose={close} />}
      <div
        aria-live="polite"
        // Top-right, below the navbar: at the bottom they would cover the chat composer.
        className="pointer-events-none fixed inset-x-4 top-24 z-60 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-6 sm:items-end"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl bg-navy px-4 py-3 text-sm text-white shadow-lift"
          >
            {t.kind === 'success' && <CheckCircle2 size={18} className="mt-px shrink-0 text-teal" aria-hidden />}
            {t.kind === 'info' && <Info size={18} className="mt-px shrink-0 text-teal" aria-hidden />}
            {t.kind === 'error' && <AlertCircle size={18} className="mt-px shrink-0 text-teal" aria-hidden />}
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="-m-1 grid size-6 shrink-0 place-items-center rounded-md text-white/60 hover:text-white"
            >
              <X size={15} />
            </button>
          </div>
        ))}
      </div>
    </UIContext.Provider>
  )
}

function ConfirmDialog({ opts, onClose }: { opts: ConfirmOptions; onClose: (ok: boolean) => void }) {
  const [typed, setTyped] = useState('')
  const cancelRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const canConfirm = !opts.requireText || typed.trim().toLowerCase() === opts.requireText.toLowerCase()

  // Focus the safe choice (or the confirmation field); Esc cancels.
  useEffect(() => {
    ;(opts.requireText ? inputRef.current : cancelRef.current)?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [opts.requireText, onClose])

  const danger = opts.tone === 'danger'
  return (
    <div className="fixed inset-0 z-70 grid place-items-center p-4">
      <button type="button" aria-label="Cancel" className="absolute inset-0 bg-navy/40 backdrop-blur-[2px]" onClick={() => onClose(false)} />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={opts.message ? 'confirm-message' : undefined}
        className="relative w-full max-w-md rounded-3xl bg-white p-6 shadow-lift sm:p-7"
      >
        <h2 id="confirm-title" className="text-xl font-extrabold tracking-tight">{opts.title}</h2>
        {opts.message && (
          <p id="confirm-message" className="mt-2 text-sm leading-relaxed text-navy/70">{opts.message}</p>
        )}
        {opts.requireText && (
          <label className="mt-5 block text-sm">
            <span className="font-semibold">
              Type <span className="font-bold text-teal">{opts.requireText}</span> to confirm
            </span>
            <input
              ref={inputRef}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && canConfirm && onClose(true)}
              autoComplete="off"
              className="mt-1.5 w-full rounded-xl border border-navy/15 px-4 py-2.5 outline-none focus:border-teal focus:ring-4 focus:ring-teal/15"
            />
          </label>
        )}
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            onClick={() => onClose(false)}
            className="rounded-full border-2 border-navy/15 px-5 py-2.5 text-sm font-semibold hover:border-navy/40"
          >
            {opts.cancelLabel ?? 'Cancel'}
          </button>
          <button
            type="button"
            disabled={!canConfirm}
            onClick={() => onClose(true)}
            className={`rounded-full px-5 py-2.5 text-sm font-semibold text-white transition disabled:opacity-40 ${
              danger ? 'bg-navy hover:bg-navy/90' : 'bg-teal hover:brightness-110'
            }`}
          >
            {opts.confirmLabel ?? 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}
