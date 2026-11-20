import { FileUp, LoaderCircle } from 'lucide-react'
import { type DragEvent, useRef, useState } from 'react'

import { type DocumentInfo, MAX_UPLOAD_MB, uploadDocument } from '../../lib/admin'

type Notice = { kind: 'ok' | 'info' | 'error'; text: string }

/** Drag-and-drop / click-to-choose PDF upload with progress. */
export default function UploadCard({ onUploaded }: { onUploaded: (doc: DocumentInfo) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  const upload = async (file: File | undefined) => {
    if (!file || progress !== null) return
    setNotice(null)
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    if (!isPdf) return setNotice({ kind: 'error', text: `“${file.name}” is not a PDF.` })
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      return setNotice({ kind: 'error', text: `“${file.name}” is larger than ${MAX_UPLOAD_MB} MB.` })
    }
    setProgress(0)
    try {
      const res = await uploadDocument(file, setProgress)
      onUploaded(res.document)
      setNotice(
        res.created
          ? { kind: 'ok', text: `“${file.name}” uploaded. Processing has started; this can take a few minutes.` }
          : { kind: 'info', text: `“${file.name}” was already uploaded, so nothing new was added.` },
      )
    } catch (e) {
      setNotice({ kind: 'error', text: (e as Error).message })
    } finally {
      setProgress(null)
      if (input.current) input.current.value = ''
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDrag(false)
    void upload(e.dataTransfer.files[0])
  }

  const busy = progress !== null
  return (
    <section aria-label="Upload legislation" className="rounded-3xl border border-navy/5 bg-white p-6 shadow-soft sm:p-8">
      <h2 className="text-lg font-bold">Upload legislation</h2>
      <p className="mt-1 text-sm text-navy/65">
        PDFs of Acts, codes or the Constitution (up to {MAX_UPLOAD_MB} MB). LawBuddy reads the
        structure, finds every section and makes it searchable.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={`mt-5 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
          drag ? 'border-teal bg-teal/10' : 'border-navy/15 bg-teal/[0.03]'
        }`}
      >
        {busy ? (
          <>
            <LoaderCircle className="animate-spin text-teal" size={32} aria-hidden />
            <p className="mt-3 text-sm font-semibold">Uploading… {Math.round((progress ?? 0) * 100)}%</p>
            <div className="mt-3 h-1.5 w-56 overflow-hidden rounded-full bg-navy/10">
              <div className="h-full rounded-full bg-teal transition-[width]" style={{ width: `${(progress ?? 0) * 100}%` }} />
            </div>
          </>
        ) : (
          <>
            <FileUp className="text-teal" size={34} strokeWidth={1.75} aria-hidden />
            <p className="mt-3 font-semibold">Drag a PDF here</p>
            <p className="text-sm text-navy/60">or</p>
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="mt-2 rounded-full bg-navy px-5 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5"
            >
              Choose a file
            </button>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-label="Choose a PDF to upload"
          onChange={(e) => void upload(e.target.files?.[0])}
        />
      </div>

      {notice && (
        <p
          role={notice.kind === 'error' ? 'alert' : 'status'}
          className={`mt-4 rounded-xl px-4 py-3 text-sm ${
            notice.kind === 'error' ? 'border border-navy/15 bg-navy/5 font-medium' : 'bg-teal/10'
          }`}
        >
          {notice.text}
        </p>
      )}
    </section>
  )
}
