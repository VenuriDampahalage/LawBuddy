import { SendHorizontal, Square } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'

/** Auto-growing message box. Enter sends, Shift+Enter adds a new line. */
export default function Composer({ onSend, onStop, streaming }: {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
}) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])

  useEffect(() => {
    if (!streaming) ref.current?.focus()
  }, [streaming])

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const t = text.trim()
    if (!t || streaming) return
    onSend(t)
    setText('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl px-4 sm:px-6">
      <div className="flex items-end gap-2 rounded-3xl border border-navy/10 bg-white p-2 pl-5 shadow-lift focus-within:border-teal/60">
        <label htmlFor="composer" className="sr-only">Your question</label>
        <textarea
          id="composer"
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={4000}
          placeholder="Ask about Sri Lankan law…"
          className="max-h-[200px] min-h-11 flex-1 resize-none bg-transparent py-2.5 text-[15px] leading-relaxed outline-none placeholder:text-navy/40"
        />
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop answering"
            className="grid size-11 shrink-0 place-items-center rounded-full bg-navy text-white transition hover:opacity-90"
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!text.trim()}
            aria-label="Send"
            className="grid size-11 shrink-0 place-items-center rounded-full bg-teal text-white transition hover:scale-105 disabled:scale-100 disabled:opacity-40"
          >
            <SendHorizontal size={20} />
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-navy/50">
        LawBuddy gives general legal information, not legal advice.
      </p>
    </form>
  )
}
