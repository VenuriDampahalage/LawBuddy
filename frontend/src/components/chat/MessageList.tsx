import {
  AlertCircle,
  Check,
  Copy,
  LoaderCircle,
  RotateCcw,
  Scale,
  Square,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import { useState } from 'react'

import { answerAsText, type Citation, sendFeedback, type Stage, STAGE_LABEL } from '../../lib/chat'
import { useUI } from '../../lib/ui'
import Answer from './Answer'
import Sources from './Sources'

export type UIMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  /** assistant message still being generated */
  pending?: boolean
  stage?: Stage
  error?: string
  stopped?: boolean
  feedback?: 1 | -1 | null
}

type Props = {
  messages: UIMessage[]
  conversationId: string | undefined
  onRetry: (assistantId: string) => void
  onFeedback: (messageId: string, value: 1 | -1 | null) => void
}

export default function MessageList({ messages, conversationId, onRetry, onFeedback }: Props) {
  return (
    <ol className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8 sm:px-6">
      {messages.map((m) =>
        m.role === 'user' ? (
          <li key={m.id} className="flex justify-end">
            <p className="max-w-[85%] rounded-3xl rounded-br-lg bg-navy px-5 py-3 text-[15px] leading-relaxed whitespace-pre-wrap text-white">
              {m.content}
            </p>
          </li>
        ) : (
          <AssistantMessage
            key={m.id}
            m={m}
            conversationId={conversationId}
            onRetry={onRetry}
            onFeedback={onFeedback}
          />
        ),
      )}
    </ol>
  )
}

function AssistantMessage({ m, conversationId, onRetry, onFeedback }: {
  m: UIMessage
  conversationId: string | undefined
  onRetry: (id: string) => void
  onFeedback: Props['onFeedback']
}) {
  const [highlight, setHighlight] = useState<number | null>(null)
  const prefix = `src-${m.id}`

  const cite = (ref: number) => {
    document.getElementById(`${prefix}-${ref}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    setHighlight(ref)
    window.setTimeout(() => setHighlight((h) => (h === ref ? null : h)), 1800)
  }

  return (
    <li className="flex gap-3">
      <span
        aria-hidden
        className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-teal/15 text-teal"
      >
        <Scale size={16} />
      </span>
      <div className="min-w-0 flex-1">
        {m.content && <Answer text={m.content} onCite={cite} />}

        {m.pending && (
          <p role="status" className="mt-1 inline-flex items-center gap-2 text-sm font-medium text-navy/60">
            <LoaderCircle className="animate-spin text-teal" size={16} aria-hidden />
            {m.content ? 'Writing…' : STAGE_LABEL[m.stage ?? 'understanding']}
          </p>
        )}

        {m.stopped && (
          <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-navy/5 px-3 py-1 text-xs font-semibold text-navy/60">
            <Square size={10} fill="currentColor" aria-hidden />
            {m.content ? 'Stopped' : 'Stopped before the answer started'}
          </p>
        )}

        {m.error && (
          <div role="alert" className="mt-2 flex flex-wrap items-center gap-3 rounded-2xl border border-navy/15 bg-navy/5 px-4 py-3 text-sm">
            <AlertCircle size={18} className="shrink-0" aria-hidden />
            <span className="flex-1">{m.error}</span>
            <button
              type="button"
              onClick={() => onRetry(m.id)}
              className="inline-flex items-center gap-1.5 font-semibold text-teal hover:underline"
            >
              <RotateCcw size={14} aria-hidden /> Try again
            </button>
          </div>
        )}

        {!m.pending && <Sources citations={m.citations} idPrefix={prefix} highlight={highlight} />}

        {!m.pending && !m.error && m.content && (
          <AnswerActions m={m} conversationId={conversationId} onFeedback={onFeedback} />
        )}
      </div>
    </li>
  )
}

/** Copy + 👍/👎 under a finished answer. */
function AnswerActions({ m, conversationId, onFeedback }: {
  m: UIMessage
  conversationId: string | undefined
  onFeedback: Props['onFeedback']
}) {
  const { toast } = useUI()
  const [copied, setCopied] = useState(false)
  // Ratings need the saved message id (stopped answers and in-flight ones have none yet).
  const canRate = !!conversationId && !m.id.startsWith('tmp-') && !m.stopped

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answerAsText(m.content, m.citations))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast('Couldn’t copy. Select the text and copy it instead.', 'error')
    }
  }

  const rate = async (value: 1 | -1) => {
    if (!conversationId) return
    const previous = m.feedback ?? null
    const next = previous === value ? null : value // clicking the same thumb again clears it
    onFeedback(m.id, next)
    try {
      await sendFeedback(conversationId, m.id, next ?? 0)
      if (next === -1) toast('Thanks for letting us know. This helps improve LawBuddy’s answers.', 'info')
    } catch (e) {
      onFeedback(m.id, previous)
      toast((e as Error).message, 'error')
    }
  }

  const btn = 'grid size-8 place-items-center rounded-lg text-navy/50 transition hover:bg-navy/5 hover:text-navy'
  return (
    <div className="mt-3 flex items-center gap-1" aria-label="Answer actions">
      <button type="button" onClick={copy} aria-label={copied ? 'Copied' : 'Copy answer'} title="Copy answer" className={btn}>
        {copied ? <Check size={16} className="text-teal" /> : <Copy size={16} />}
      </button>
      {canRate && (
        <>
          <button
            type="button"
            onClick={() => void rate(1)}
            aria-label="Helpful"
            aria-pressed={m.feedback === 1}
            title="Helpful"
            className={`${btn} ${m.feedback === 1 ? 'text-teal' : ''}`}
          >
            <ThumbsUp size={16} fill={m.feedback === 1 ? 'currentColor' : 'none'} />
          </button>
          <button
            type="button"
            onClick={() => void rate(-1)}
            aria-label="Not helpful"
            aria-pressed={m.feedback === -1}
            title="Not helpful"
            className={`${btn} ${m.feedback === -1 ? 'text-navy' : ''}`}
          >
            <ThumbsDown size={16} fill={m.feedback === -1 ? 'currentColor' : 'none'} />
          </button>
        </>
      )}
    </div>
  )
}
