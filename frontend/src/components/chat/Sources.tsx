import { ChevronDown, ExternalLink, History } from 'lucide-react'
import { useState } from 'react'

import { type Citation, openCitationPdf, pageLabel } from '../../lib/chat'
import { useUI } from '../../lib/ui'

/** Source cards under an answer. `highlight` flashes the card a citation chip points to. */
export default function Sources({ citations, idPrefix, highlight }: {
  citations: Citation[]
  idPrefix: string
  highlight: number | null
}) {
  if (!citations.length) return null
  return (
    <section aria-label="Sources" className="mt-5">
      <h3 className="text-xs font-bold tracking-wide text-navy/50 uppercase">Sources</h3>
      <ol className="mt-2 grid gap-2">
        {[...citations].sort((a, b) => a.ref - b.ref).map((c) => (
          <SourceCard key={c.ref} c={c} id={`${idPrefix}-${c.ref}`} active={highlight === c.ref} />
        ))}
      </ol>
    </section>
  )
}

function SourceCard({ c, id, active }: { c: Citation; id: string; active: boolean }) {
  const { toast } = useUI()
  const [open, setOpen] = useState(false)
  const act = c.act_title
  return (
    <li
      id={id}
      className={`scroll-mt-24 rounded-2xl border bg-white p-3.5 transition-shadow ${
        active ? 'border-teal shadow-[0_0_0_4px_rgb(42_157_143/0.15)]' : 'border-navy/10'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="grid size-6 shrink-0 place-items-center rounded-md bg-teal/15 text-xs font-bold text-teal">
          {c.ref}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold">
            {c.provision ?? 'Provision'}
            {c.heading && <span className="font-semibold text-navy/70"> — {c.heading}</span>}
          </p>
          <p className="mt-0.5 truncate text-xs text-navy/60" title={act}>
            {act}
            {pageLabel(c) && <> · {pageLabel(c)}</>}
          </p>
          {c.amended_by.length > 0 && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-teal">
              <History size={13} aria-hidden /> Later amended by {c.amended_by.join(', ')}
            </p>
          )}
          {open && (
            <blockquote className="mt-2 border-l-2 border-teal/40 pl-3 text-xs leading-relaxed whitespace-pre-line text-navy/75">
              {c.excerpt}
              {c.excerpt.length >= 400 ? '…' : ''}
            </blockquote>
          )}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="inline-flex items-center gap-1 text-xs font-semibold text-navy/70 hover:text-navy"
            >
              <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
              {open ? 'Hide text' : 'Show text'}
            </button>
            {c.document_id && (
              <button
                type="button"
                onClick={async () => {
                  if (!(await openCitationPdf(c))) toast('Sorry, the PDF could not be opened.', 'error')
                }}
                className="inline-flex items-center gap-1 text-xs font-semibold text-teal hover:underline"
              >
                <ExternalLink size={13} aria-hidden /> Open PDF{c.page_start ? ` at page ${c.page_start}` : ''}
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  )
}
