import { ShieldAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../lib/auth'
import Spinner from './Spinner'

/** Renders children only for signed-in users (and admins, if `admin`); otherwise redirects
 *  to /login?next=<where they were going>. */
export default function RequireAuth({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="grid min-h-[50vh] place-items-center">
        <Spinner label="Checking your session" />
      </div>
    )
  }
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  if (admin && user.role !== 'admin') {
    return (
      <section className="mx-auto max-w-md px-6 py-32 text-center">
        <ShieldAlert className="mx-auto text-teal" size={40} aria-hidden />
        <h1 className="mt-4 text-2xl font-extrabold">Admins only</h1>
        <p className="mt-2 text-navy/70">Your account doesn't have access to the admin panel.</p>
        <Link to="/chat" className="mt-6 inline-block font-semibold text-teal hover:underline">
          Go to chat
        </Link>
      </section>
    )
  }
  return children
}
