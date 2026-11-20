import {
  AlertTriangle,
  Check,
  ChevronDown,
  LoaderCircle,
  Pencil,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  Undo2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import Spinner from '../../components/Spinner'
import {
  editProposal,
  listProposals,
  OPERATION_LABEL,
  type Proposal,
  proposalAction,
  type ProposalFilter,
  scanAmendments,
} from '../../lib/admin'
import { diffWords } from '../../lib/diff'
import { useUI } from '../../lib/ui'

const FILTERS: { value: ProposalFilter; label: string }[] = [
  { value: 'open', label: 'To review' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'all', label: 'All' },
]

type Data = Awaited<ReturnType<typeof listProposals>>

export default function AdminAmendments() {
  const { toast } = useUI()
  const [filter, setFilter] = useState<ProposalFilter>('open')
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await listProposals(filter))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [filter])

  useEffect(() => {
    let cancelled = false
    listProposals(filter)
      .then((d) => !cancelled && (setData(d), setError(null)))
      .catch((e) => !cancelled && setError((e as Error).message))
    return () => {
      cancelled = true
    }
  }, [filter])

  // While a scan runs on the server, refresh every few seconds so new proposals appear.
  const scanning = data?.scanning ?? false
  useEffect(() => {
    if (!scanning) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [scanning, load])

  const scan = async () => {
    try {
      await scanAmendments()
      toast('Scanning amendment Acts… new proposals will appear here.', 'info')
      setData((d) => (d ? { ...d, scanning: true } : d))
      window.setTimeout(() => void load(), 1500)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const replace = (p: Proposal) => {
    setData((d) => {
      if (!d) return d
      const stillShown = filter === 'all' || (filter === 'open' ? ['pending', 'needs_attention'].includes(p.status) : p.status === filter)
      return { ...d, items: stillShown ? d.items.map((x) => (x.id === p.id ? p : x)) : d.items.filter((x) => x.id !== p.id) }
    })
    void listProposals(filter).then((d) => setData((cur) => (cur ? { ...cur, counts: d.counts } : d)))
  }

  const c = data?.counts ?? {}
  const toReview = (c.pending ?? 0) + (c.needs_attention ?? 0)

  return (
    <div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-3">
          {[
            { n: toReview, label: 'To review' },
            { n: c.approved ?? 0, label: 'Approved' },
            { n: c.rejected ?? 0, label: 'Rejected' },
          ].map((s) => (
            <div key={s.label} className="rounded-2xl border border-navy/5 bg-white px-5 py-3 shadow-soft">
              <p className="text-2xl font-extrabold tabular-nums">{data ? s.n : '–'}</p>
              <p className="text-xs text-navy/60">{s.label}</p>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div role="radiogroup" aria-label="Filter amendments" className="flex gap-1 rounded-full border border-navy/5 bg-white p-1 shadow-soft">
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
          <button
            type="button"
            onClick={() => void scan()}
            disabled={scanning}
            className="inline-flex items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {scanning ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <ScanSearch size={16} aria-hidden />}
            {scanning ? 'Scanning…' : 'Scan for amendments'}
          </button>
        </div>
      </div>

      <p className="mt-4 max-w-3xl text-sm text-navy/60">
        Amendment Acts change sections of the laws they amend. LawBuddy reads each amending section,
        proposes the updated text, and checks the words against both Acts. Nothing changes until you
        approve it; approved versions can be reverted.
      </p>

      {error && <p role="alert" className="mt-6 text-sm">Couldn’t load amendments: {error}</p>}
      {!data && !error && (
        <div className="grid place-items-center py-16">
          <Spinner label="Loading amendments" />
        </div>
      )}
      {data && data.items.length === 0 && (
        <p className="mt-6 rounded-2xl border border-dashed border-navy/15 p-8 text-center text-sm text-navy/60">
          {filter === 'open' ? 'Nothing to review. All amendments found so far have been handled.' : 'Nothing here yet.'}
        </p>
      )}
      {data && data.items.length > 0 && (
        <ul className="mt-5 space-y-4">
          {data.items.map((p) => (
            <ProposalCard key={p.id} p={p} onChange={replace} />
          ))}
        </ul>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: Proposal['status'] }) {
  const map = {
    pending: ['Ready to review', 'bg-teal/10 text-teal'],
    needs_attention: ['Needs attention', 'border border-navy/30'],
    approved: ['Approved', 'bg-teal/15 text-teal'],
    rejected: ['Rejected', 'bg-navy/5 text-navy/60'],
  } as const
  const [label, cls] = map[status]
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${cls}`}>{label}</span>
}

function ProposalCard({ p, onChange }: { p: Proposal; onChange: (p: Proposal) => void }) {
  const { confirm, toast } = useUI()
  const [busy, setBusy] = useState(false)
  const [showSource, setShowSource] = useState(false)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(p.proposed_text)
  const [heading, setHeading] = useState(p.proposed_heading ?? '')

  const isNew = p.operation === 'insert_section'
  const target = p.new_provision ?? p.target_provision
  const parts = useMemo(() => diffWords(p.current_text, p.proposed_text), [p.current_text, p.proposed_text])
  const headingChanged = (p.current_heading ?? '') !== (p.proposed_heading ?? '')

  const run = async (action: 'approve' | 'reject' | 'reopen' | 'revert', done: string) => {
    setBusy(true)
    try {
      onChange(await proposalAction(p.id, action))
      toast(done)
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const approve = async () => {
    const ok = await confirm({
      title: `Apply this amendment to ${target}?`,
      message: isNew
        ? `${target} will be added to ${p.target_act} and LawBuddy will start answering from it.`
        : `The new text becomes the current version of ${target}. The previous version is kept as history, and you can revert this later.`,
      confirmLabel: 'Approve',
    })
    if (ok) await run('approve', `${target} updated. LawBuddy now answers from the amended text.`)
  }

  const save = async () => {
    setBusy(true)
    try {
      onChange(await editProposal(p.id, text, heading.trim() || null))
      setEditing(false)
      toast('Proposed text saved.')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const open = p.status === 'pending' || p.status === 'needs_attention'
  const btn = 'inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition disabled:opacity-40'

  return (
    <li className={`rounded-2xl border bg-white p-4 sm:p-6 ${p.status === 'needs_attention' ? 'border-navy/40' : 'border-navy/10'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-extrabold">{target}</span>
            {(p.proposed_heading || p.current_heading) && (
              <span className="font-semibold text-navy/70">— {p.proposed_heading || p.current_heading}</span>
            )}
          </p>
          <p className="mt-0.5 text-sm text-navy/60">{p.target_act}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-navy/5 px-2.5 py-0.5 text-xs font-semibold">{OPERATION_LABEL[p.operation] ?? p.operation}</span>
          {p.edited && <span className="rounded-full bg-navy/5 px-2.5 py-0.5 text-xs font-semibold">Edited</span>}
          <StatusBadge status={p.status} />
        </div>
      </div>

      <p className="mt-3 text-sm">
        <span className="font-semibold">Amended by</span> {p.amendment_act}, {p.amendment_provision}
        {p.amendment_heading && <span className="text-navy/60"> ({p.amendment_heading})</span>}
      </p>
      <p className="mt-1 text-sm text-navy/70">{p.summary}</p>

      {p.problem && (
        <p className="mt-3 flex gap-2 rounded-xl bg-navy/5 px-4 py-3 text-sm">
          <AlertTriangle size={18} className="mt-px shrink-0" aria-hidden />
          <span><span className="font-semibold">Couldn’t apply automatically.</span> {p.problem} Edit the text, then approve.</span>
        </p>
      )}

      <button
        type="button"
        onClick={() => setShowSource((s) => !s)}
        aria-expanded={showSource}
        className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-navy/70 hover:text-navy"
      >
        <ChevronDown size={16} className={`transition-transform ${showSource ? 'rotate-180' : ''}`} aria-hidden />
        {showSource ? 'Hide' : 'Show'} the amending text
      </button>
      {showSource && (
        <blockquote className="mt-2 max-h-72 overflow-y-auto border-l-2 border-teal/50 pl-4 text-sm leading-relaxed whitespace-pre-line text-navy/75">
          {p.amendment_text}
        </blockquote>
      )}

      <div className="mt-4">
        <p className="text-xs font-bold tracking-wide text-navy/50 uppercase">
          {isNew ? 'New section' : p.status === 'approved' ? 'Change applied' : 'Proposed change'}
        </p>
        {headingChanged && !editing && (
          <p className="mt-2 text-sm">
            Heading:{' '}
            {p.current_heading && <del className="rounded bg-navy/10 px-1 text-navy/60">{p.current_heading}</del>}{' '}
            {p.proposed_heading && <ins className="rounded bg-teal/20 px-1 no-underline">{p.proposed_heading}</ins>}
          </p>
        )}
        {editing ? (
          <div className="mt-2 space-y-3">
            <label className="block text-sm">
              <span className="font-semibold">Heading</span>
              <input
                value={heading}
                onChange={(e) => setHeading(e.target.value)}
                className="mt-1 w-full rounded-xl border border-navy/15 px-3 py-2 outline-none focus:border-teal focus:ring-4 focus:ring-teal/15"
              />
            </label>
            <label className="block text-sm">
              <span className="font-semibold">Text of {target} after the amendment</span>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={Math.min(18, Math.max(6, text.split('\n').length + 2))}
                className="mt-1 w-full rounded-xl border border-navy/15 px-3 py-2 font-mono text-sm leading-relaxed outline-none focus:border-teal focus:ring-4 focus:ring-teal/15"
              />
            </label>
          </div>
        ) : (
          <Diff parts={parts} />
        )}
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {open && !editing && (
          <>
            <button type="button" disabled={busy || p.status === 'needs_attention'} onClick={() => void approve()}
              className={`${btn} bg-teal text-white hover:brightness-110`}
              title={p.status === 'needs_attention' ? 'Edit the text first' : undefined}>
              {busy ? <RefreshCw size={15} className="animate-spin" aria-hidden /> : <Check size={15} aria-hidden />} Approve
            </button>
            <button type="button" disabled={busy} onClick={() => setEditing(true)} className={`${btn} border-2 border-navy/15 hover:border-navy/40`}>
              <Pencil size={15} aria-hidden /> Edit
            </button>
            <button type="button" disabled={busy} onClick={() => void run('reject', `${target}: amendment rejected.`)}
              className={`${btn} text-navy/70 hover:bg-navy/5 hover:text-navy`}>
              <X size={15} aria-hidden /> Reject
            </button>
          </>
        )}
        {editing && (
          <>
            <button type="button" disabled={busy || !text.trim()} onClick={() => void save()} className={`${btn} bg-navy text-white`}>
              <Check size={15} aria-hidden /> Save text
            </button>
            <button type="button" onClick={() => { setEditing(false); setText(p.proposed_text); setHeading(p.proposed_heading ?? '') }}
              className={`${btn} text-navy/70 hover:bg-navy/5`}>
              Cancel
            </button>
          </>
        )}
        {p.status === 'approved' && (
          <button type="button" disabled={busy} onClick={() => void run('revert', `${target}: back to the previous version.`)}
            className={`${btn} border-2 border-navy/15 hover:border-navy/40`}>
            <Undo2 size={15} aria-hidden /> Revert
          </button>
        )}
        {p.status === 'rejected' && (
          <button type="button" disabled={busy} onClick={() => void run('reopen', `${target}: back in the review list.`)}
            className={`${btn} border-2 border-navy/15 hover:border-navy/40`}>
            <RotateCcw size={15} aria-hidden /> Reopen
          </button>
        )}
      </div>
    </li>
  )
}

/** Word diff with long unchanged stretches collapsed (click to expand). */
function Diff({ parts }: { parts: ReturnType<typeof diffWords> }) {
  const [full, setFull] = useState(false)
  const KEEP = 18
  return (
    <div className="mt-2 rounded-xl border border-navy/10 bg-teal/[0.03] p-4 text-sm leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => {
        if (part.type === 'added') return <ins key={i} className="rounded bg-teal/20 px-0.5 no-underline">{part.text}</ins>
        if (part.type === 'removed') return <del key={i} className="rounded bg-navy/10 px-0.5 text-navy/55">{part.text}</del>
        const words = part.text.split(/(\s+)/)
        if (full || words.length <= KEEP * 4) return <span key={i}>{part.text}</span>
        const head = i === 0 ? '' : words.slice(0, KEEP * 2).join('')
        const tail = i === parts.length - 1 ? '' : words.slice(-KEEP * 2).join('')
        return (
          <span key={i}>
            {head}
            <button type="button" onClick={() => setFull(true)} className="mx-1 rounded-full bg-navy/5 px-2 text-xs font-semibold text-navy/60 hover:text-navy">
              … unchanged text …
            </button>
            {tail}
          </span>
        )
      })}
    </div>
  )
}
