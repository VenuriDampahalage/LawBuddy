import type { ReactNode } from 'react'

/** Centered white form card for the sign-in and sign-up pages. The Sri Lankan landscape
 *  background is drawn by SiteLayout behind the whole page. */
export default function AuthShell({ title, subtitle, children }: {
  title: string
  subtitle: ReactNode
  children: ReactNode
}) {
  return (
    // m-auto centres the card when it fits and keeps the top/bottom padding when it doesn't
    // (align-items:center would push a tall card up against the navbar).
    <section className="flex flex-1 px-4 py-8 sm:py-12">
      <div className="m-auto w-full max-w-md rounded-3xl border border-navy/5 bg-white/95 px-6 py-10 shadow-lift backdrop-blur-sm sm:px-10 sm:py-12">
        <h1 className="text-3xl font-extrabold tracking-tight">{title}</h1>
        <p className="mt-2 text-navy/65">{subtitle}</p>
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}
