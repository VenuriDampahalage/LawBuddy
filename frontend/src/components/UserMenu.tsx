import { LogOut, MessageCircle, ShieldCheck, UserRound } from 'lucide-react'
import { startTransition, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import type { User } from '../lib/api'
import { initials, useAuth } from '../lib/auth'

/** Avatar button with a small dropdown: chat, admin panel (admins), sign out. */
export default function UserMenu({ user }: { user: User }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [avatarFailed, setAvatarFailed] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  const item = 'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium hover:bg-teal/10'

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="grid size-10 place-items-center overflow-hidden rounded-full bg-navy text-sm font-bold text-white ring-teal/40 transition hover:ring-4"
      >
        {user.avatar_url && !avatarFailed ? (
          <img
            src={user.avatar_url}
            alt=""
            className="size-full object-cover"
            referrerPolicy="no-referrer"
            onError={() => setAvatarFailed(true)}
          />
        ) : (
          initials(user)
        )}
      </button>

      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-64 rounded-2xl border border-navy/5 bg-white p-2 shadow-lift">
          <div className="border-b border-navy/5 px-3 pt-2 pb-3">
            <p className="truncate text-sm font-bold">{user.full_name || 'Signed in'}</p>
            <p className="truncate text-xs text-navy/60">{user.email}</p>
            {user.role === 'admin' && (
              <span className="mt-2 inline-block rounded-full bg-teal/10 px-2 py-0.5 text-xs font-semibold text-teal">
                Admin
              </span>
            )}
          </div>
          <div className="pt-2">
            <Link to="/chat" role="menuitem" onClick={() => setOpen(false)} className={item}>
              <MessageCircle size={18} className="text-teal" aria-hidden /> Chat
            </Link>
            <Link to="/account" role="menuitem" onClick={() => setOpen(false)} className={item}>
              <UserRound size={18} className="text-teal" aria-hidden /> Account
            </Link>
            {user.role === 'admin' && (
              <Link to="/admin" role="menuitem" onClick={() => setOpen(false)} className={item}>
                <ShieldCheck size={18} className="text-teal" aria-hidden /> Admin panel
              </Link>
            )}
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                // Same transition as the router's navigation: otherwise the protected page
                // re-renders signed-out first and redirects to /login instead of home.
                startTransition(() => {
                  navigate('/')
                  logout()
                })
              }}
              className={item}
            >
              <LogOut size={18} className="text-teal" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
