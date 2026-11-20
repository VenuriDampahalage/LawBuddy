import { type FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import AuthShell from '../components/AuthShell'
import { Field, FormError, SubmitButton } from '../components/Form'
import GoogleSection from '../components/GoogleSection'
import { ApiError } from '../lib/api'
import { safeNext, useAuth } from '../lib/auth'

export default function Login() {
  const { user, login, loginWithGoogle } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = safeNext(params.get('next'))

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) return <Navigate to={next} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'That email and password don’t match an account.'
          : (err as Error).message,
      )
    } finally {
      setBusy(false)
    }
  }

  const google = async (credential: string) => {
    setError(null)
    setBusy(true)
    try {
      await loginWithGoogle(credential)
      navigate(next, { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle={
        params.get('next')
          ? 'Sign in to continue to LawBuddy.'
          : 'Sign in to ask questions and see your conversations.'
      }
    >
      <GoogleSection text="signin_with" onCredential={google} />
      <form onSubmit={submit} className="space-y-5">
        <FormError message={error} />
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <SubmitButton busy={busy}>{busy ? 'Signing in…' : 'Sign in'}</SubmitButton>
      </form>

      <p className="mt-8 text-center text-sm text-navy/70">
        New to LawBuddy?{' '}
        <Link
          to={`/register${params.get('next') ? `?next=${encodeURIComponent(next)}` : ''}`}
          className="font-semibold text-teal hover:underline"
        >
          Create an account
        </Link>
      </p>
    </AuthShell>
  )
}
