import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  FileText,
  LoaderCircle,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'

import {
  type DocumentDetail,
  type DocumentInfo,
  displayName,
  getDocument,
  IN_PROGRESS,
  KIND_LABEL,
  STEPS,
  timeAgo,
} from '../../lib/admin'
import { openDocumentPdf } from '../../lib/chat'
import { useUI } from '../../lib/ui'

export function StatusBadge({ status }: { status: DocumentInfo['status'] }) {
  if (status === 'ready') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-teal/15 px-2.5 py-1 text-xs font-bold text-teal">
        <CheckCircle2 size={14} aria-hidden /> Ready
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-navy/30 px-2.5 py-1 text-xs font-bold">
        <AlertCircle size={14} aria-hidden /> Failed
      </span>
    )
  }
  const label = STEPS.find((s) => s.status === status)?.label ?? status
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-navy/5 px-2.5 py-1 text-xs font-bold">
      <LoaderCircle size={14} className="animate-spin text-teal" aria-hidden /> {label}
    </span>
  )
}

/** Queued → Reading PDF → Finding sections → Indexing → Ready */
function Steps({ status }: { status: DocumentInfo['status'] }) {
  const current = STEPS.findIndex((s) => s.status === status)
  return (
    <ol className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" aria-label="Processing steps">
      {STEPS.map((s, i) => (
        <li key={s.status} className="flex items-center gap-2">
          <span
            className={`size-2 rounded-full ${
              i < current ? 'bg-teal' : i === current ? 'animate-pulse bg-teal' : 'bg-navy/15'
            }`}
            aria-hidden
          />
          <span className={i === current ? 'font-bold' : i < current ? 'text-navy/70' : 'text-navy/40'}>
            {s.label}
          </span>
          {i < STEPS.length - 1 && (
            <ArrowRight size={12} className={i < current ? 'text-teal' : 'text-navy/25'} aria-hidden />
          )}
        </li>
      ))}
    </ol>
  )
}

export default function DocumentRow({ doc, onReprocess, onDelete }: {
  doc: DocumentInfo
  onReprocess: (d: DocumentInfo) => void
  onDelete: (d: DocumentInfo) => void
}) {
  const { toast } = useUI()
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<DocumentDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const busy = IN_PROGRESS.includes(doc.status)

  const toggle = async () => {
    const next = !open
    setOpen(next)
    // (Re)load the Acts whenever the row is opened, so a re-processed document is current.
    if (next) {
      setDetailError(null)
      try {
        setDetail(await getDocument(doc.id))
      } catch (e) {
        setDetailError((e as Error).message)
      }
    }
  }

  const name = displayName(doc.filename)
  return (
    <li className="rounded-2xl border border-navy/10 bg-white">
      <div className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-6 sm:p-5">
        <div className="flex min-w-0 items-start gap-3">
          <FileText className="mt-0.5 shrink-0 text-teal" size={22} strokeWidth={1.75} aria-hidden />
          <div className="min-w-0">
            <p className="truncate font-bold" title={name}>{name}</p>
            <p className="mt-0.5 text-xs text-navy/60">
              {doc.page_count ? `${doc.page_count} pages · ` : ''}
              {doc.status === 'ready' ? `${doc.acts} Act${doc.acts === 1 ? '' : 's'} · ${doc.chunks.toLocaleString()} chunks · ` : ''}
              uploaded {timeAgo(doc.created_at)}
            </p>
            {busy && <Steps status={doc.status} />}
            {doc.status === 'failed' && doc.error && (
              <p className="mt-2 rounded-lg bg-navy/5 px-3 py-2 text-xs leading-relaxed">{doc.error}</p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          <StatusBadge status={doc.status} />
          <button
            type="button"
            onClick={async () => {
              if (!(await openDocumentPdf(doc.id))) toast('Sorry, the PDF could not be opened.', 'error')
            }}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-navy/70 hover:bg-navy/5 hover:text-navy"
          >
            <ExternalLink size={14} aria-hidden /> PDF
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onReprocess(doc)}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-navy/70 hover:bg-navy/5 hover:text-navy disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <RotateCcw size={14} aria-hidden /> Re-process
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDelete(doc)}
            aria-label={`Delete ${name}`}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-navy/70 hover:bg-navy/5 hover:text-navy disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <Trash2 size={14} aria-hidden /> Delete
          </button>
          {doc.status === 'ready' && (
            <button
              type="button"
              onClick={toggle}
              aria-expanded={open}
              aria-label={open ? 'Hide Acts' : 'Show Acts'}
              className="grid size-8 place-items-center rounded-full text-navy/70 hover:bg-navy/5 hover:text-navy"
            >
              <ChevronDown size={18} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {open && (
        <div className="border-t border-navy/5 px-4 py-4 sm:px-5">
          {detailError && <p className="text-sm">{detailError}</p>}
          {!detail && !detailError && <p className="text-sm text-navy/60">Loading…</p>}
          {detail && (
            <>
              <h3 className="text-xs font-bold tracking-wide text-navy/50 uppercase">Acts in this PDF</h3>
              <ul className="mt-2 divide-y divide-navy/5">
                {detail.act_list.map((a) => (
                  <li key={a.id} className="grid gap-1 py-2.5 text-sm sm:grid-cols-[minmax(0,1fr)_9rem_6rem_6rem] sm:items-center sm:gap-4">
                    <span className="font-semibold">{a.title}</span>
                    <span>
                      <span className="rounded-full bg-teal/10 px-2 py-0.5 text-xs font-semibold text-teal">
                        {KIND_LABEL[a.kind]}
                      </span>
                    </span>
                    <span className="text-xs text-navy/65">{a.sections} sections</span>
                    <span className="text-xs text-navy/65">
                      {a.page_start ? `pp. ${a.page_start}–${a.page_end}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </li>
  )
}
