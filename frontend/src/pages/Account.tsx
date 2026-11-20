import { KeyRound, MessageSquare, Trash2, UserRound } from 'lucide-react'
import { type FormEvent, type ReactNode, startTransition, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Field, SubmitButton } from '../components/Form'
import * as api from '../lib/api'
import { initials, useAuth } from '../lib/auth'
import { useUI } from '../lib/ui'

const MIN_PASSWORD = 8

function Card({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="rounded-3xl border border-navy/5 bg-white p-6 shadow-soft sm:p-8">
      <h2 className="flex items-center gap-2.5 text-lg font-bold">
        <span className="text-teal">{icon}</span> {title}
      </h2>
      <div className="mt-5">{children}</div>
    </section>
  )
}

export default function Account() {
  const { user } = useAuth()
  if (!user) return null // RequireAuth guarantees a user; keeps TypeScript happy
  return (
    <section className="mx-auto max-w-3xl px-4 pt-10 sm:px-6">
      <h1 className="text-3xl font-extrabold tracking-tight">Your account</h1>
      <p className="mt-1 text-navy/65">Manage your profile, password and data.</p>
      <div className="mt-8 space-y-6">
        <Profile user={user} />
        <Password user={user} />
        <DangerZone user={user} />
      </div>
    </section>
  )
}

function Profile({ user }: { user: api.User }) {
  const { updateUser } = useAuth()
  const { toast } = useUI()
  const [name, setName] = useState(user.full_name ?? '')
  const [busy, setBusy] = useState(false)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      updateUser(await api.updateProfile(name.trim()))
      toast('Profile saved.')
    } catch (err) {
      toast((err as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card icon={<UserRound size={20} />} title="Profile">
      <div className="flex items-center gap-4">
        <span className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-full bg-navy text-xl font-bold text-white">
          {user.avatar_url ? (
            <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" className="size-full object-cover" />
          ) : (
            initials(user)
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate font-semibold">{user.email}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {user.google_linked && (
              <span className="rounded-full bg-teal/10 px-2.5 py-0.5 text-xs font-semibold text-teal">Google sign-in</span>
            )}
            {user.has_password && (
              <span className="rounded-full bg-teal/10 px-2.5 py-0.5 text-xs font-semibold text-teal">Email & password</span>
            )}
            {user.role === 'admin' && (
              <span className="rounded-full bg-navy px-2.5 py-0.5 text-xs font-semibold text-white">Admin</span>
            )}
          </div>
        </div>
      </div>
      <form onSubmit={save} className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-end">
        <Field
          label="Full name"
          className="flex-1"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
          autoComplete="name"
        />
        <div className="sm:w-40">
          <SubmitButton busy={busy}>{busy ? 'Saving…' : 'Save'}</SubmitButton>
        </div>
      </form>
    </Card>
  )
}

function Password({ user }: { user: api.User }) {
  const { updateUser } = useAuth()
  const { toast } = useUI()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const nextError = touched && next.length < MIN_PASSWORD ? `Use at least ${MIN_PASSWORD} characters.` : undefined
  const confirmError = touched && confirmPw !== next ? 'Passwords don’t match.' : undefined

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (next.length < MIN_PASSWORD || confirmPw !== next) return
    setBusy(true)
    try {
      await api.changePassword(user.has_password ? current : null, next)
      toast(user.has_password ? 'Password changed.' : 'Password set. You can now also sign in with your email.')
      if (!user.has_password) updateUser({ ...user, has_password: true })
      setCurrent('')
      setNext('')
      setConfirmPw('')
      setTouched(false)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card icon={<KeyRound size={20} />} title={user.has_password ? 'Change password' : 'Set a password'}>
      {!user.has_password && (
        <p className="-mt-1 mb-5 text-sm text-navy/65">
          You sign in with Google. Setting a password lets you also sign in with your email address.
        </p>
      )}
      <form onSubmit={submit} className="space-y-4">
        {user.has_password && (
          <Field
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            error={error ?? undefined}
          />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={next}
            onChange={(e) => setNext(e.target.value)}
            hint={`At least ${MIN_PASSWORD} characters`}
            error={nextError}
          />
          <Field
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            error={confirmError}
          />
        </div>
        {!user.has_password && error && <p role="alert" className="text-sm font-semibold">{error}</p>}
        <div className="sm:w-56">
          <SubmitButton busy={busy}>{busy ? 'Saving…' : user.has_password ? 'Change password' : 'Set password'}</SubmitButton>
        </div>
      </form>
    </Card>
  )
}

function DangerZone({ user }: { user: api.User }) {
  const { logout } = useAuth()
  const { confirm, toast } = useUI()
  const navigate = useNavigate()

  const remove = async () => {
    const ok = await confirm({
      title: 'Delete your account?',
      message:
        'This permanently deletes your account and all your conversations. It can’t be undone.',
      confirmLabel: 'Delete my account',
      tone: 'danger',
      requireText: user.email,
    })
    if (!ok) return
    try {
      await api.deleteAccount(user.email)
      startTransition(() => {
        navigate('/')
        logout()
      })
      toast('Your account has been deleted.')
    } catch (err) {
      toast((err as Error).message, 'error')
    }
  }

  return (
    <Card icon={<MessageSquare size={20} />} title="Your data">
      <p className="text-sm leading-relaxed text-navy/70">
        LawBuddy stores your account details and your conversations so you can come back to them.
        You can delete single conversations from the{' '}
        <Link to="/chat" className="font-semibold text-teal hover:underline">chat sidebar</Link>, or
        everything at once by deleting your account. See the{' '}
        <Link to="/privacy" className="font-semibold text-teal hover:underline">Privacy Policy</Link>{' '}
        for details.
      </p>
      <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-navy/15 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-bold">Delete account</p>
          <p className="text-sm text-navy/65">Permanently removes your account and conversations.</p>
        </div>
        <button
          type="button"
          onClick={() => void remove()}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full border-2 border-navy px-5 py-2 text-sm font-semibold transition hover:bg-navy hover:text-white"
        >
          <Trash2 size={16} aria-hidden /> Delete account
        </button>
      </div>
    </Card>
  )
}
