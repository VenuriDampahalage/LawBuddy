import { Home, LogOut, MessageSquare, Plus, ShieldCheck, Trash2, UserRound } from 'lucide-react'
import { startTransition } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'

import { initials, useAuth } from '../../lib/auth'
import type { Conversation } from '../../lib/chat'

/** Navy sidebar: new chat, conversation history, account. */
export default function Sidebar({ conversations, loading, activeId, onNew, onDelete, onNavigate }: {
  conversations: Conversation[]
  loading: boolean
  activeId: string | undefined
  onNew: () => void
  onDelete: (c: Conversation) => void
  onNavigate?: () => void
}) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="flex h-full flex-col bg-navy text-white">
      <div className="px-5 pt-5">
        <Link to="/" className="text-2xl font-extrabold tracking-tight" onClick={onNavigate}>
          Law<span className="text-teal">Buddy</span>
        </Link>
        <button
          type="button"
          onClick={onNew}
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-full bg-teal px-4 py-2.5 text-sm font-semibold transition hover:brightness-110"
        >
          <Plus size={18} aria-hidden /> New chat
        </button>
      </div>

      <nav aria-label="Conversations" className="mt-6 min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        <h2 className="px-2 text-xs font-bold tracking-wide text-white/50 uppercase">Recent</h2>
        {loading && <p className="px-2 pt-3 text-sm text-white/50">Loading…</p>}
        {!loading && conversations.length === 0 && (
          <p className="px-2 pt-3 text-sm text-white/50">No conversations yet.</p>
        )}
        <ul className="mt-2 space-y-0.5">
          {conversations.map((c) => (
            <li key={c.id} className="group relative">
              <NavLink
                to={`/chat/${c.id}`}
                onClick={onNavigate}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-xl py-2 pr-9 pl-2 text-sm transition ${
                    isActive || c.id === activeId ? 'bg-white/10 font-semibold' : 'text-white/80 hover:bg-white/5'
                  }`
                }
              >
                <MessageSquare size={15} className="shrink-0 text-teal" aria-hidden />
                <span className="truncate">{c.title || 'New conversation'}</span>
              </NavLink>
              <button
                type="button"
                onClick={() => onDelete(c)}
                aria-label={`Delete “${c.title || 'New conversation'}”`}
                className="absolute top-1/2 right-1.5 grid size-7 -translate-y-1/2 place-items-center rounded-lg text-white/60 opacity-0 transition group-hover:opacity-100 hover:bg-white/10 hover:text-white focus-visible:opacity-100"
              >
                <Trash2 size={15} />
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {user && (
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-3 px-2 py-2">
            <span className="grid size-9 shrink-0 place-items-center overflow-hidden rounded-full bg-teal text-sm font-bold">
              {user.avatar_url ? (
                <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" className="size-full object-cover" />
              ) : (
                initials(user)
              )}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{user.full_name || user.email}</p>
              <p className="truncate text-xs text-white/50">{user.role === 'admin' ? 'Admin' : user.email}</p>
            </div>
          </div>
          <div className="mt-1 flex gap-1">
            <Link to="/" title="Home" aria-label="Home" className="grid h-9 flex-1 place-items-center rounded-xl text-white/70 hover:bg-white/10 hover:text-white">
              <Home size={17} />
            </Link>
            <Link to="/account" title="Account" aria-label="Account" className="grid h-9 flex-1 place-items-center rounded-xl text-white/70 hover:bg-white/10 hover:text-white">
              <UserRound size={17} />
            </Link>
            {user.role === 'admin' && (
              <Link to="/admin" title="Admin panel" aria-label="Admin panel" className="grid h-9 flex-1 place-items-center rounded-xl text-white/70 hover:bg-white/10 hover:text-white">
                <ShieldCheck size={17} />
              </Link>
            )}
            <button
              type="button"
              title="Sign out"
              aria-label="Sign out"
              onClick={() => startTransition(() => { navigate('/'); logout() })}
              className="grid h-9 flex-1 place-items-center rounded-xl text-white/70 hover:bg-white/10 hover:text-white"
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
