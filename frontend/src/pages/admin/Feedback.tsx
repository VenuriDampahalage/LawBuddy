import { ChevronDown, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useEffect, useState } from 'react'

import Answer from '../../components/chat/Answer'
import Sources from '../../components/chat/Sources'
import Spinner from '../../components/Spinner'
import { type FeedbackItem, type FeedbackRating, listFeedback, timeAgo } from '../../lib/admin'

const FILTERS: { value: FeedbackRating; label: string }[] = [
  { value: 'not_helpful', label: 'Not helpful' },
  { value: 'helpful', label: 'Helpful' },
  { value: 'all', label: 'All' },
]

export default function AdminFeedback() {
  const [rating, setRating] = useState<FeedbackRating>('not_helpful')
  const [data, setData] = useState<Awaited<ReturnType<typeof listFeedback>> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listFeedback(rating)
      .then((d) => {
        if (cancelled) return
        setData(d)
        setError(null)
      })
      .catch((e) => !cancelled && setError((e as Error).message))
    return () => {
      cancelled = true
    }
  }, [rating])

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-3">
          <div className="rounded-2xl border border-navy/5 bg-white px-5 py-3 shadow-soft">
            <p className="flex items-center gap-2 text-2xl font-extrabold tabular-nums">
              <ThumbsDown size={20} className="text-navy" aria-hidden /> {data?.not_helpful ?? '–'}
            </p>
            <p className="text-xs text-navy/60">Not helpful</p>
          </div>
          <div className="rounded-2xl border border-navy/5 bg-white px-5 py-3 shadow-soft">
            <p className="flex items-center gap-2 text-2xl font-extrabold tabular-nums">
              <ThumbsUp size={20} className="text-teal" aria-hidden /> {data?.helpful ?? '–'}
            </p>
            <p className="text-xs text-navy/60">Helpful</p>
          </div>
        </div>
        <div role="radiogroup" aria-label="Filter feedback" className="flex gap-1 self-start rounded-full border border-navy/5 bg-white p-1 shadow-soft sm:self-auto">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="radio"
              aria-checked={rating === f.value}
              onClick={() => setRating(f.value)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${
                rating === f.value ? 'bg-teal/15 text-teal' : 'text-navy/60 hover:text-navy'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-4 text-sm text-navy/60">
        Answers users rated, with the question that was asked. Use them to spot missing laws or
        answers that need a better prompt.
      </p>

      {error && <p role="alert" className="mt-6 text-sm">Couldn’t load feedback: {error}</p>}
      {!data && !error && (
        <div className="grid place-items-center py-16">
          <Spinner label="Loading feedback" />
        </div>
      )}
      {data && data.items.length === 0 && (
        <p className="mt-6 rounded-2xl border border-dashed border-navy/15 p-8 text-center text-sm text-navy/60">
          No {rating === 'helpful' ? 'helpful' : rating === 'all' ? '' : 'unhelpful'} ratings yet.
        </p>
      )}
      {data && data.items.length > 0 && (
        <ul className="mt-4 space-y-4">
          {data.items.map((item) => (
            <FeedbackCard key={item.message_id} item={item} />
          ))}
        </ul>
      )}
    </div>
  )
}

function FeedbackCard({ item }: { item: FeedbackItem }) {
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState<number | null>(null)
  const prefix = `fb-${item.message_id}`

  const cite = (ref: number) => {
    setOpen(true)
    setHighlight(ref)
    window.setTimeout(() => {
      document.getElementById(`${prefix}-${ref}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 50)
    window.setTimeout(() => setHighlight((h) => (h === ref ? null : h)), 1800)
  }

  return (
    <li className="rounded-2xl border border-navy/10 bg-white p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-navy/60">
        <span className="inline-flex items-center gap-2 font-semibold">
          {item.rating === -1 ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-navy/30 px-2.5 py-0.5 text-navy">
              <ThumbsDown size={13} aria-hidden /> Not helpful
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-teal/10 px-2.5 py-0.5 text-teal">
              <ThumbsUp size={13} aria-hidden /> Helpful
            </span>
          )}
          {item.user_email}
        </span>
        <span>{timeAgo(item.answered_at)}</span>
      </div>

      <p className="mt-4 text-xs font-bold tracking-wide text-navy/50 uppercase">Question</p>
      <p className="mt-1 rounded-2xl bg-navy px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-white">
        {item.question ?? '(question not found)'}
      </p>

      <p className="mt-4 text-xs font-bold tracking-wide text-navy/50 uppercase">Answer</p>
      <div className={`relative mt-1 ${open ? '' : 'max-h-40 overflow-hidden'}`}>
        <Answer text={item.answer} onCite={cite} />
        {!open && <div aria-hidden className="absolute inset-x-0 bottom-0 h-16 bg-linear-to-t from-white to-white/0" />}
      </div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-teal hover:underline"
      >
        <ChevronDown size={16} className={`transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
        {open
          ? 'Show less'
          : `Show full answer${item.citations.length ? ` and ${item.citations.length} source${item.citations.length === 1 ? '' : 's'}` : ''}`}
      </button>
      {open && <Sources citations={item.citations} idPrefix={prefix} highlight={highlight} />}
    </li>
  )
}
