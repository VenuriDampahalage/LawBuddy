import { Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { useAuth } from '../lib/auth'
import Logo from './Logo'
import UserMenu from './UserMenu'

const LINKS = [
  { label: 'Home', to: '/' },
  { label: 'Chat', to: '/chat' },
  { label: 'Features', to: '/#features' },
  { label: 'About', to: '/#about' },
]

export default function Navbar() {
  const { pathname, hash } = useLocation()
  const { user, loading } = useAuth()
  const [open, setOpen] = useState(false)
  // No "Sign in" button on the sign-in / sign-up pages themselves.
  const onAuthPage = pathname === '/login' || pathname === '/register'

  const isActive = (to: string) => {
    const [path, anchor] = to.split('#')
    if (anchor) return pathname === '/' && hash === `#${anchor}`
    if (path === '/') return pathname === '/' && !hash
    return pathname.startsWith(path)
  }

  const linkClass = (to: string) =>
    `rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
      isActive(to) ? 'bg-teal/10 text-teal' : 'text-navy hover:text-teal'
    }`

  return (
    <header className="sticky top-4 z-50 px-4">
      <nav
        aria-label="Main"
        className="mx-auto flex max-w-6xl items-center justify-between rounded-2xl border border-navy/5 bg-white/90 px-5 py-3 shadow-soft backdrop-blur"
      >
        <Logo />

        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <li key={l.label}>
              <Link to={l.to} className={linkClass(l.to)}>
                {l.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          {user ? (
            <UserMenu user={user} />
          ) : (
            !loading && !onAuthPage && (
              <Link
                to="/login"
                className="hidden rounded-full border-2 border-navy px-5 py-1.5 text-sm font-bold text-navy transition-colors hover:bg-navy hover:text-white sm:inline-block"
              >
                Sign in
              </Link>
            )
          )}
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-label={open ? 'Close menu' : 'Open menu'}
            className="rounded-lg p-2 text-navy md:hidden"
          >
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </nav>

      {open && (
        <div className="mx-auto mt-2 max-w-6xl rounded-2xl border border-navy/5 bg-white p-3 shadow-soft md:hidden">
          <ul className="flex flex-col gap-1">
            {[...LINKS, ...(user || onAuthPage ? [] : [{ label: 'Sign in', to: '/login' }])].map((l) => (
              <li key={l.label}>
                <Link to={l.to} onClick={() => setOpen(false)} className={`block ${linkClass(l.to)}`}>
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </header>
  )
}
