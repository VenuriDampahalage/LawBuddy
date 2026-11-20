import { FilePenLine, FileStack, MessageSquareWarning, Users } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const TABS = [
  { to: '/admin', label: 'Documents', icon: FileStack, end: true },
  { to: '/admin/amendments', label: 'Amendments', icon: FilePenLine, end: false },
  { to: '/admin/users', label: 'Users', icon: Users, end: false },
  { to: '/admin/feedback', label: 'Feedback', icon: MessageSquareWarning, end: false },
]

/** Admin panel frame: title + tabs; each tab is its own route. */
export default function AdminLayout() {
  return (
    <section className="mx-auto max-w-6xl px-4 pt-10 sm:px-6">
      <h1 className="text-3xl font-extrabold tracking-tight">Admin panel</h1>
      <p className="mt-1 text-navy/65">
        Manage the legislation LawBuddy answers from, its amendments, user accounts and answer feedback.
      </p>
      <nav aria-label="Admin sections" className="mt-6 flex gap-1 overflow-x-auto rounded-full border border-navy/5 bg-white p-1 shadow-soft sm:w-fit">
        {TABS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                isActive ? 'bg-navy text-white' : 'text-navy/70 hover:bg-navy/5 hover:text-navy'
              }`
            }
          >
            <Icon size={16} aria-hidden /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-8">
        <Outlet />
      </div>
    </section>
  )
}
