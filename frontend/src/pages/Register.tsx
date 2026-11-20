import { type FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import AuthShell from '../components/AuthShell'
import { Field, FormError, SubmitButton } from '../components/Form'
import GoogleSection from '../components/GoogleSection'
import { safeNext, useAuth } from '../lib/auth'

const MIN_PASSWORD = 8

export default function Register() {
  const { user, register, loginWithGoogle } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = safeNext(params.get('next'))

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) return <Navigate to={next} replace />

  const passwordError =
    touched && password.length < MIN_PASSWORD ? `Use at least ${MIN_PASSWORD} characters.` : undefined
  const confirmError = touched && confirm !== password ? 'Passwords don’t match.' : undefined

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (password.length < MIN_PASSWORD || confirm !== password) return
    setBusy(true)
    try {
      await register(email.trim(), password, name.trim())
      navigate(next, { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const google = async (credential: string) => {
    setError(null)
    setBusy(true)
    try {
      await loginWithGoogle(credential)       // creates the account on first use
      navigate(next, { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="It’s free. Ask about Sri Lankan law in plain English.">
      <GoogleSection text="signup_with" onCredential={google} />
      <form onSubmit={submit} className="space-y-5">
        <FormError message={error} />
        <Field
          label="Full name"
          hint="Optional"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
        />
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint={`At least ${MIN_PASSWORD} characters`}
            error={passwordError}
          />
          <Field
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={confirmError}
          />
        </div>
        <SubmitButton busy={busy}>{busy ? 'Creating account…' : 'Create account'}</SubmitButton>
        <p className="text-center text-xs leading-relaxed text-navy/55">
          By creating an account you agree to the{' '}
          <Link to="/terms" className="font-semibold text-teal hover:underline">Terms of Use</Link> and{' '}
          <Link to="/privacy" className="font-semibold text-teal hover:underline">Privacy Policy</Link>.
          LawBuddy gives general legal information, not legal advice.
        </p>
      </form>

      <p className="mt-8 text-center text-sm text-navy/70">
        Already have an account?{' '}
        <Link
          to={`/login${params.get('next') ? `?next=${encodeURIComponent(next)}` : ''}`}
          className="font-semibold text-teal hover:underline"
        >
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}
