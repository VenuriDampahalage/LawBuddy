import {
  BookOpen,
  FileText,
  FolderOpen,
  type LucideIcon,
  MessageCircle,
  MessagesSquare,
  Quote,
  RefreshCw,
  Scale,
  Search,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import goddess from '../assets/goddess.webp'
import { getLaws, type Law } from '../lib/api'
import { useAuth } from '../lib/auth'

type Item = { icon: LucideIcon; title: string; text: string }

const AROUND_LEFT: Item[] = [
  { icon: FileText, title: 'Law documents', text: 'Sri Lankan Acts, codes and the Constitution.' },
  { icon: Scale, title: 'Ask legal questions', text: 'Describe your situation in plain English.' },
]
const AROUND_RIGHT: Item[] = [
  { icon: BookOpen, title: 'Legal knowledge', text: 'Answers grounded in the actual legislation.' },
  { icon: Quote, title: 'Cited sources', text: 'Every answer shows the exact section and page.' },
]

const FEATURES: Item[] = [
  { icon: MessagesSquare, title: 'AI legal chat', text: 'Ask in natural language and get clear, structured answers.' },
  { icon: RefreshCw, title: 'Always up to date', text: 'Tracks later amendments, so you see the law as it stands.' },
  { icon: FolderOpen, title: 'Document library', text: 'Legislation is uploaded and maintained by administrators.' },
  { icon: ShieldCheck, title: 'Private & simple', text: 'Your conversations are visible only to you.' },
]

const STEPS = [
  { title: 'Ask', text: 'Describe your problem or ask about a law, in everyday words.' },
  { title: 'LawBuddy searches the law', text: 'It finds the provisions that apply, including definitions and amendments.' },
  { title: 'Get a cited answer', text: 'A plain-language explanation, with every point linked to its section and page.' },
]

function FloatCard({ icon: Icon, title, text }: Item) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-navy/5 bg-white p-4 shadow-soft">
      <Icon className="mt-0.5 shrink-0 text-teal" size={26} strokeWidth={1.75} aria-hidden />
      <div>
        <h3 className="text-sm font-bold">{title}</h3>
        <p className="mt-0.5 text-sm leading-snug text-navy/65">{text}</p>
      </div>
    </div>
  )
}

function AskBar() {
  const [q, setQ] = useState('')
  const navigate = useNavigate()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const question = q.trim()
    navigate(question ? `/chat?q=${encodeURIComponent(question)}` : '/chat')
  }
  return (
    <form
      onSubmit={submit}
      className="relative z-10 mx-auto flex w-full max-w-2xl items-center gap-2 rounded-full border border-navy/5 bg-white p-2 pl-6 shadow-lift"
    >
      <Search className="shrink-0 text-navy/40" size={20} aria-hidden />
      <label htmlFor="ask" className="sr-only">Ask a legal question</label>
      <input
        id="ask"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Ask anything about Sri Lankan law…"
        className="min-w-0 flex-1 bg-transparent py-2 text-base outline-none placeholder:text-navy/45"
        maxLength={4000}
      />
      <button
        type="submit"
        aria-label="Ask LawBuddy"
        className="grid size-11 shrink-0 place-items-center rounded-full bg-teal text-white transition-transform hover:scale-105"
      >
        <SendHorizontal size={20} />
      </button>
    </form>
  )
}

function LawsCovered() {
  const [laws, setLaws] = useState<Law[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const ctrl = new AbortController()
    getLaws(ctrl.signal).then(setLaws).catch((e) => e.name !== 'AbortError' && setFailed(true))
    return () => ctrl.abort()
  }, [])

  // The library list shows the main laws; amendment Acts are summarised as a count.
  const main = laws?.filter((l) => l.kind !== 'amendment') ?? []
  const amendments = laws?.filter((l) => l.kind === 'amendment').length ?? 0

  return (
    <div className="rounded-3xl border border-navy/5 bg-white p-6 shadow-soft sm:p-8">
      <h3 className="text-lg font-bold">Laws in the library</h3>
      {failed && <p className="mt-3 text-sm text-navy/60">The list is unavailable right now.</p>}
      {!laws && !failed && <p className="mt-3 text-sm text-navy/60">Loading…</p>}
      {laws && (
        <>
          <ul className="mt-4 space-y-3">
            {main.map((l) => (
              <li key={l.title} className="flex items-start gap-3 text-sm">
                <span className="mt-1.5 size-2 shrink-0 rounded-full bg-teal" aria-hidden />
                <span>{l.title}</span>
              </li>
            ))}
          </ul>
          {amendments > 0 && (
            <p className="mt-4 border-t border-navy/5 pt-4 text-sm text-navy/60">
              Plus {amendments} amending Act{amendments === 1 ? '' : 's'}, so answers reflect later
              changes to the law.
            </p>
          )}
        </>
      )}
    </div>
  )
}

export default function Home() {
  const { user, loading } = useAuth()
  return (
    <>
      {/* ---------------- Hero ---------------- */}
      <section className="mx-auto max-w-6xl px-6 pt-14 text-center sm:pt-20">
        <p className="inline-flex items-center gap-2 rounded-full border border-teal/40 bg-white px-4 py-1.5 text-sm font-semibold">
          <Sparkles size={16} className="text-teal" aria-hidden />
          AI-powered legal assistant
        </p>

        <h1 className="mt-6 text-5xl leading-[1.05] font-extrabold tracking-tight sm:text-7xl">
          Your Personal
          <br />
          <span className="text-teal">Legal Assistant.</span>
        </h1>

        <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-navy/70">
          Ask questions about Sri Lankan law, get clear explanations, and see the exact sections
          they come from.
        </p>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            to="/chat"
            className="inline-flex items-center gap-2 rounded-full bg-navy px-7 py-3.5 font-semibold text-white shadow-soft transition-transform hover:-translate-y-0.5"
          >
            <MessageCircle size={20} aria-hidden />
            Chat with LawBuddy
          </Link>
          {/* Second button: visitors sign in; admins get the admin panel; users need neither. */}
          {!loading && (!user || user.role === 'admin') && (
            <Link
              to={user ? '/admin' : '/login'}
              className="inline-flex items-center gap-2 rounded-full border-2 border-navy bg-white px-7 py-3 font-semibold transition-colors hover:bg-navy hover:text-white"
            >
              {user && <ShieldCheck size={20} aria-hidden />}
              {user ? 'Admin Panel' : 'Sign in'}
            </Link>
          )}
        </div>
      </section>

      {/* ---------------- Goddess + floating cards ---------------- */}
      <section aria-label="What LawBuddy offers" className="mx-auto max-w-6xl px-6 pt-10">
        <div className="relative lg:grid lg:grid-cols-[1fr_auto_1fr] lg:items-center lg:gap-6">
          <div className="hidden flex-col gap-24 lg:flex lg:items-end">
            {AROUND_LEFT.map((c, i) => (
              <div key={c.title} className={`w-72 ${i === 1 ? 'lg:-mr-6' : ''}`}>
                <FloatCard {...c} />
              </div>
            ))}
          </div>

          <div className="relative mx-auto w-full max-w-105">
            <div
              aria-hidden
              className="absolute top-[22%] left-1/2 aspect-square w-[92%] -translate-x-1/2 rounded-full bg-teal/15"
            />
            <img
              src={goddess}
              alt="Lady Justice holding silver scales and a sword"
              width={900}
              height={1071}
              className="relative w-full select-none"
              draggable={false}
            />
          </div>

          <div className="hidden flex-col gap-24 lg:flex lg:items-start">
            {AROUND_RIGHT.map((c, i) => (
              <div key={c.title} className={`w-72 ${i === 1 ? 'lg:-ml-6' : ''}`}>
                <FloatCard {...c} />
              </div>
            ))}
          </div>
        </div>

        <div className="-mt-10 px-0 sm:-mt-14">
          <AskBar />
        </div>

        {/* On smaller screens the floating cards sit in a grid under the image */}
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:hidden">
          {[...AROUND_LEFT, ...AROUND_RIGHT].map((c) => (
            <FloatCard key={c.title} {...c} />
          ))}
        </div>
      </section>

      {/* ---------------- Key features ---------------- */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-28 px-6 pt-24">
        <h2 className="mx-auto w-fit rounded-full bg-teal/10 px-5 py-2 text-lg font-bold">
          Key features
        </h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <article key={title} className="rounded-2xl border border-navy/5 bg-white p-6 shadow-soft">
              <Icon className="text-teal" size={30} strokeWidth={1.75} aria-hidden />
              <h3 className="mt-4 text-lg font-bold">{title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-navy/65">{text}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---------------- About ---------------- */}
      <section id="about" className="mx-auto max-w-6xl scroll-mt-28 px-6 pt-24">
        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-3xl font-extrabold tracking-tight">How LawBuddy works</h2>
            <ol className="mt-8 space-y-6">
              {STEPS.map((s, i) => (
                <li key={s.title} className="flex gap-4">
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-navy text-sm font-bold text-white">
                    {i + 1}
                  </span>
                  <div>
                    <h3 className="font-bold">{s.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-navy/65">{s.text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-8 rounded-2xl bg-teal/10 p-4 text-sm leading-relaxed">
              LawBuddy gives general legal information based on the legislation in its library. It
              is not legal advice. For your specific situation, speak to an Attorney-at-Law.
            </p>
          </div>
          <LawsCovered />
        </div>
      </section>
    </>
  )
}
