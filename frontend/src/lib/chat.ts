/** Chat API: conversations, messages and the streaming (Server-Sent Events) answer. */

import { API_BASE, ApiError, apiFetch, backendUrl, tokenStore } from './api'

export type Citation = {
  ref: number
  citation: string
  act_title: string
  provision: string | null
  heading: string | null
  document_id: string | null
  page_start: number | null
  page_end: number | null
  printed_page_start: string | null
  printed_page_end: string | null
  excerpt: string
  amended_by: string[]
}

export type Conversation = { id: string; title: string | null; created_at: string; updated_at: string }

export type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  status: 'complete' | 'stopped'
  feedback: 1 | -1 | null
  created_at: string
}

export type Stage = 'understanding' | 'searching' | 'searching_again' | 'checking' | 'writing'

export type StreamEvent =
  | { type: 'status'; stage: Stage }
  | { type: 'token'; text: string }
  | { type: 'done'; answer: string; citations: Citation[]; message_id?: string }
  | { type: 'error'; message: string }

export const listConversations = () => apiFetch<Conversation[]>('/conversations')
export const createConversation = () => apiFetch<Conversation>('/conversations', { method: 'POST' })
export const deleteConversation = (id: string) =>
  apiFetch<void>(`/conversations/${id}`, { method: 'DELETE' })
export const listMessages = (id: string) => apiFetch<Message[]>(`/conversations/${id}/messages`)
export const getFileLink = (documentId: string) =>
  apiFetch<{ url: string; expires_in: number }>(`/documents/${documentId}/link`)

/**
 * POST a question and read the answer as a stream of Server-Sent Events.
 * (EventSource can't POST or send an Authorization header, so we parse the stream ourselves.)
 */
export async function streamAnswer(
  conversationId: string,
  content: string,
  onEvent: (e: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${tokenStore.get() ?? ''}`,
    },
    body: JSON.stringify({ content }),
    signal,
  })
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message)
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    // Events are separated by a blank line; sse-starlette uses \r\n line endings.
    const parts = buffer.split(/\r?\n\r?\n/)
    buffer = parts.pop() ?? ''
    for (const block of parts) {
      let event = 'message'
      const data: string[] = []
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith(':')) continue // keep-alive ping
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
      }
      if (!data.length) continue
      try {
        const payload = JSON.parse(data.join('\n'))
        onEvent({ ...payload, type: payload.type ?? event } as StreamEvent)
      } catch {
        /* ignore malformed event */
      }
    }
  }
}

export const STAGE_LABEL: Record<Stage, string> = {
  understanding: 'Understanding your question…',
  searching: 'Searching the law…',
  searching_again: 'Searching more broadly…',
  checking: 'Checking which sections apply…',
  writing: 'Writing the answer…',
}

/** "p. 15" / "pp. 40–41", using printed page numbers when we have them. */
export function pageLabel(c: Citation): string {
  const a = c.printed_page_start ?? c.page_start
  const b = c.printed_page_end ?? c.page_end
  if (a == null) return ''
  return a === b || b == null ? `p. ${a}` : `pp. ${a}–${b}`
}

/** Open the cited PDF in a new tab at the cited page. Resolves false if it failed. */
export function openCitationPdf(c: Citation): Promise<boolean> {
  return c.document_id ? openDocumentPdf(c.document_id, c.page_start ?? 1) : Promise.resolve(false)
}

/** Open a stored PDF in a new tab (at a page) via a short-lived signed link.
 *  Resolves false if it failed, so the caller can tell the user. */
export async function openDocumentPdf(documentId: string, page = 1): Promise<boolean> {
  // Open the tab synchronously (inside the click) so pop-up blockers allow it.
  const tab = window.open('', '_blank')
  try {
    const { url } = await getFileLink(documentId)
    // The server returns "/api/documents/…": point it at the backend, then make it absolute
    // (the blank tab has no base URL to resolve a relative one against).
    const target = `${new URL(backendUrl(url), window.location.origin).href}#page=${page}`
    if (tab) tab.location.href = target
    else window.location.href = target
    return true
  } catch {
    tab?.close()
    return false
  }
}

export const sendFeedback = (conversationId: string, messageId: string, value: 1 | -1 | 0) =>
  apiFetch<Message>(`/conversations/${conversationId}/messages/${messageId}/feedback`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  })

/** Answer + numbered sources as plain text, for the Copy button. */
export function answerAsText(content: string, citations: Citation[]): string {
  if (!citations.length) return content
  const sources = [...citations]
    .sort((a, b) => a.ref - b.ref)
    .map((c) => `[${c.ref}] ${c.citation}${c.heading ? ` (${c.heading})` : ''}`)
  return `${content}\n\nSources:\n${sources.join('\n')}`
}
