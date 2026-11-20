import { BookOpen, FileStack, Layers, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import DocumentRow from '../../components/admin/DocumentRow'
import UploadCard from '../../components/admin/UploadCard'
import Spinner from '../../components/Spinner'
import {
  deleteDocument,
  type DocumentInfo,
  displayName,
  IN_PROGRESS,
  listDocuments,
  reprocessDocument,
} from '../../lib/admin'
import { useUI } from '../../lib/ui'

const POLL_MS = 3000

export default function AdminDocuments() {
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { confirm, toast } = useUI()

  const load = useCallback(async () => {
    try {
      setDocs(await listDocuments())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    listDocuments()
      .then(setDocs)
      .catch((e) => setError((e as Error).message))
  }, [])

  // While anything is processing, refresh every few seconds to move the step tracker.
  const processing = docs?.some((d) => IN_PROGRESS.includes(d.status)) ?? false
  useEffect(() => {
    if (!processing) return
    const t = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(t)
  }, [processing, load])

  const onUploaded = (doc: DocumentInfo) =>
    setDocs((ds) => (ds?.some((d) => d.id === doc.id) ? ds : [doc, ...(ds ?? [])]))

  const reprocess = async (d: DocumentInfo) => {
    const name = displayName(d.filename)
    const ok = await confirm({
      title: `Re-process “${name}”?`,
      message: 'Its sections will be rebuilt from the PDF. This can take a few minutes, and LawBuddy can’t answer from this document until it finishes.',
      confirmLabel: 'Re-process',
    })
    if (!ok) return
    try {
      const updated = await reprocessDocument(d.id)
      setDocs((ds) => ds?.map((x) => (x.id === d.id ? updated : x)) ?? null)
      toast(`Re-processing “${name}”…`, 'info')
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const remove = async (d: DocumentInfo) => {
    const name = displayName(d.filename)
    const ok = await confirm({
      title: `Delete “${name}”?`,
      message: 'Its Acts will no longer be used to answer questions, and the stored PDF is removed. This can’t be undone.',
      confirmLabel: 'Delete document',
      tone: 'danger',
    })
    if (!ok) return
    try {
      await deleteDocument(d.id)
      setDocs((ds) => ds?.filter((x) => x.id !== d.id) ?? null)
      toast(`“${name}” deleted.`)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const ready = docs?.filter((d) => d.status === 'ready') ?? []
  const stats = [
    { icon: FileStack, label: 'Documents', value: docs?.length ?? 0 },
    { icon: ShieldCheck, label: 'Ready to answer from', value: ready.length },
    { icon: BookOpen, label: 'Acts', value: ready.reduce((n, d) => n + d.acts, 0) },
    { icon: Layers, label: 'Searchable chunks', value: ready.reduce((n, d) => n + d.chunks, 0) },
  ]

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(({ icon: Icon, label, value }) => (
          <div key={label} className="rounded-2xl border border-navy/5 bg-white p-5 shadow-soft">
            <Icon className="text-teal" size={22} strokeWidth={1.75} aria-hidden />
            <p className="mt-3 text-2xl font-extrabold tabular-nums">{docs ? value.toLocaleString() : '–'}</p>
            <p className="text-sm text-navy/60">{label}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[22rem_minmax(0,1fr)] lg:items-start">
        <UploadCard onUploaded={onUploaded} />

        <section aria-label="Documents" className="min-w-0">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-bold">Documents</h2>
            {processing && (
              <p className="text-xs text-navy/60">Updating automatically while processing…</p>
            )}
          </div>
          {error && !docs && <p className="mt-6 text-sm">Couldn’t load documents: {error}</p>}
          {!docs && !error && (
            <div className="grid place-items-center py-16">
              <Spinner label="Loading documents" />
            </div>
          )}
          {docs && docs.length === 0 && (
            <p className="mt-4 rounded-2xl border border-dashed border-navy/15 p-8 text-center text-sm text-navy/60">
              No documents yet. Upload your first legislation PDF.
            </p>
          )}
          {docs && docs.length > 0 && (
            <ul className="mt-4 space-y-3">
              {docs.map((d) => (
                <DocumentRow key={d.id} doc={d} onReprocess={reprocess} onDelete={remove} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  )
}
