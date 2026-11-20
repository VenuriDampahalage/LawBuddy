import { AlertCircle, Eye, EyeOff } from 'lucide-react'
import { type InputHTMLAttributes, type ReactNode, useId, useState } from 'react'

import Spinner from './Spinner'

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  hint?: ReactNode
  error?: string
}

const inputClass =
  'w-full rounded-xl border border-navy/15 bg-white px-4 py-3 text-base outline-none transition ' +
  'placeholder:text-navy/40 focus:border-teal focus:ring-4 focus:ring-teal/15 ' +
  'aria-[invalid=true]:border-navy aria-[invalid=true]:ring-4 aria-[invalid=true]:ring-navy/10'

export function Field({ label, hint, error, type = 'text', className = '', ...props }: FieldProps) {
  const id = useId()
  const [show, setShow] = useState(false)
  const isPassword = type === 'password'
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined

  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={isPassword && show ? 'text' : type}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`${inputClass} ${isPassword ? 'pr-12' : ''}`}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? 'Hide password' : 'Show password'}
            className="absolute inset-y-0 right-0 grid w-12 place-items-center text-navy/50 hover:text-navy"
          >
            {show ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 flex items-center gap-1.5 text-sm font-semibold">
          <AlertCircle size={15} className="shrink-0" aria-hidden />
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-sm text-navy/55">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-navy/15 bg-navy/5 p-3.5 text-sm">
      <AlertCircle className="mt-0.5 shrink-0" size={18} aria-hidden />
      <span>{message}</span>
    </div>
  )
}

export function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="flex w-full items-center justify-center gap-2 rounded-full bg-navy px-6 py-3.5 font-semibold text-white shadow-soft transition hover:-translate-y-0.5 disabled:translate-y-0 disabled:opacity-70"
    >
      {busy && <Spinner label="Please wait" size={18} />}
      {children}
    </button>
  )
}
