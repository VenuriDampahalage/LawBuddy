import { Search, ShieldCheck, ShieldOff, UserCheck, UserX } from 'lucide-react'
import { useEffect, useState } from 'react'

import Spinner from '../../components/Spinner'
import { type AdminUser, listUsers, timeAgo, updateUser, type UserFilter } from '../../lib/admin'
import { initials, useAuth } from '../../lib/auth'
import { useUI } from '../../lib/ui'

const FILTERS: { value: UserFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'admins', label: 'Admins' },
  { value: 'disabled', label: 'Disabled' },
]

export default function AdminUsers() {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [filter, setFilter] = useState<UserFilter>('all')
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Search as you type, but wait for a short pause before asking the server.
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query.trim()), 300)
    return () => window.clearTimeout(t)
  }, [query])

  useEffect(() => {
    const ctrl = new AbortController()
    listUsers(debounced, filter, ctrl.signal)
      .then((u) => {
        setUsers(u)
        setError(null)
      })
      .catch((e) => (e as Error).name !== 'AbortError' && setError((e as Error).message))
    return () => ctrl.abort()
  }, [debounced, filter])

  const replace = (u: AdminUser) => setUsers((us) => us?.map((x) => (x.id === u.id ? u : x)) ?? null)

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block sm:w-80">
          <span className="sr-only">Search users</span>
          <Search size={18} className="absolute top-1/2 left-4 -translate-y-1/2 text-navy/40" aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name or email"
            className="w-full rounded-full border border-navy/10 bg-white py-2.5 pr-4 pl-11 text-sm shadow-soft outline-none focus:border-teal focus:ring-4 focus:ring-teal/15"
          />
        </label>
        <div role="radiogroup" aria-label="Filter users" className="flex gap-1 rounded-full border border-navy/5 bg-white p-1 shadow-soft">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="radio"
              aria-checked={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${
                filter === f.value ? 'bg-teal/15 text-teal' : 'text-navy/60 hover:text-navy'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p role="alert" className="mt-6 text-sm">Couldn’t load users: {error}</p>}
      {!users && !error && (
        <div className="grid place-items-center py-16">
          <Spinner label="Loading users" />
        </div>
      )}
      {users && (
        <>
          <p className="mt-6 text-sm text-navy/60">
            {users.length} {users.length === 1 ? 'account' : 'accounts'}
            {debounced && <> matching “{debounced}”</>}
          </p>
          {users.length === 0 ? (
            <p className="mt-3 rounded-2xl border border-dashed border-navy/15 p-8 text-center text-sm text-navy/60">
              No accounts found.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {users.map((u) => (
                <UserRow key={u.id} u={u} onChange={replace} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function Badge({ children, tone = 'teal' }: { children: string; tone?: 'teal' | 'navy' | 'outline' }) {
  const cls =
    tone === 'navy' ? 'bg-navy text-white' : tone === 'outline' ? 'border border-navy/30' : 'bg-teal/10 text-teal'
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{children}</span>
}

function UserRow({ u, onChange }: { u: AdminUser; onChange: (u: AdminUser) => void }) {
  const { user: me } = useAuth()
  const { confirm, toast } = useUI()
  const [busy, setBusy] = useState(false)
  const isMe = me?.id === u.id
  const name = u.full_name || u.email

  const apply = async (change: { role?: 'user' | 'admin'; is_active?: boolean }, ask: Parameters<typeof confirm>[0], done: string) => {
    if (!(await confirm(ask))) return
    setBusy(true)
    try {
      onChange(await updateUser(u.id, change))
      toast(done)
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const toggleRole = () =>
    u.role === 'admin'
      ? apply({ role: 'user' }, {
          title: `Remove admin rights from ${name}?`,
          message: 'They will keep their account and conversations but lose access to the admin panel.',
          confirmLabel: 'Remove admin',
          tone: 'danger',
        }, `${name} is no longer an admin.`)
      : apply({ role: 'admin' }, {
          title: `Make ${name} an admin?`,
          message: 'Admins can upload and delete legislation, manage user accounts and read rated answers.',
          confirmLabel: 'Make admin',
        }, `${name} is now an admin.`)

  const toggleActive = () =>
    u.is_active
      ? apply({ is_active: false }, {
          title: `Disable ${name}?`,
          message: 'They will be signed out and can’t sign in until you enable the account again. Nothing is deleted.',
          confirmLabel: 'Disable account',
          tone: 'danger',
        }, `${name} has been disabled.`)
      : apply({ is_active: true }, { title: `Enable ${name}?`, confirmLabel: 'Enable account' },
          `${name} can sign in again.`)

  const action =
    'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-navy/70 hover:bg-navy/5 hover:text-navy disabled:opacity-40 disabled:hover:bg-transparent'

  return (
    <li className={`rounded-2xl border bg-white p-4 sm:p-5 ${u.is_active ? 'border-navy/10' : 'border-dashed border-navy/25'}`}>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <span className={`grid size-11 shrink-0 place-items-center overflow-hidden rounded-full text-sm font-bold text-white ${u.is_active ? 'bg-navy' : 'bg-navy/40'}`}>
            {u.avatar_url ? (
              <img src={u.avatar_url} alt="" referrerPolicy="no-referrer" className="size-full object-cover" />
            ) : (
              initials({ ...u, created_at: u.created_at })
            )}
          </span>
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-1.5">
              <span className="truncate font-bold">{u.full_name || u.email}</span>
              {isMe && <Badge tone="navy">You</Badge>}
              {u.role === 'admin' && <Badge tone="navy">Admin</Badge>}
              {!u.is_active && <Badge tone="outline">Disabled</Badge>}
            </p>
            {u.full_name && <p className="truncate text-sm text-navy/65">{u.email}</p>}
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-navy/55">
              <span>Joined {timeAgo(u.created_at)}</span>
              <span>{u.conversations} conversation{u.conversations === 1 ? '' : 's'}</span>
              <span>{u.last_active ? `Last active ${timeAgo(u.last_active)}` : 'No questions yet'}</span>
              <span>{[u.google_linked && 'Google', u.has_password && 'Password'].filter(Boolean).join(' + ')}</span>
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1 sm:justify-end">
          <button type="button" disabled={isMe || busy} onClick={() => void toggleRole()} className={action}
            title={isMe ? 'You can’t change your own role' : undefined}>
            {u.role === 'admin' ? <ShieldOff size={14} aria-hidden /> : <ShieldCheck size={14} aria-hidden />}
            {u.role === 'admin' ? 'Remove admin' : 'Make admin'}
          </button>
          <button type="button" disabled={isMe || busy} onClick={() => void toggleActive()} className={action}
            title={isMe ? 'You can’t disable your own account' : undefined}>
            {u.is_active ? <UserX size={14} aria-hidden /> : <UserCheck size={14} aria-hidden />}
            {u.is_active ? 'Disable' : 'Enable'}
          </button>
        </div>
      </div>
    </li>
  )
}
