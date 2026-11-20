import { Menu, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import Composer from '../components/chat/Composer'
import EmptyState from '../components/chat/EmptyState'
import MessageList, { type UIMessage } from '../components/chat/MessageList'
import Sidebar from '../components/chat/Sidebar'
import Spinner from '../components/Spinner'
import { useAuth } from '../lib/auth'
import { useUI } from '../lib/ui'
import {
  type Conversation,
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  streamAnswer,
} from '../lib/chat'

const tempId = () => `tmp-${Math.random().toString(36).slice(2)}`

export default function Chat() {
  const { conversationId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { confirm, toast } = useUI()

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [convLoading, setConvLoading] = useState(true)
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [msgLoading, setMsgLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [drawer, setDrawer] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const createdHereRef = useRef<string | null>(null) // conversation we just created while sending
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  const refreshConversations = useCallback(() => {
    listConversations()
      .then(setConversations)
      .catch(() => {})
      .finally(() => setConvLoading(false))
  }, [])

  useEffect(refreshConversations, [refreshConversations])

  // Load the selected conversation's messages (unless we created it a moment ago while
  // sending: then the messages on screen are already the live ones).
  //
  // Runs only when the conversation in the URL actually differs from the one on screen.
  // (React StrictMode re-runs effects on mount; acting on every run would wipe or cancel the
  // answer that a ?q= question has just started.) Answers are stopped explicitly instead:
  // New chat, choosing another conversation, Stop.
  const shownRef = useRef<string | undefined | null>(null) // null = nothing shown yet
  useEffect(() => {
    if (shownRef.current === conversationId) return
    const previous = shownRef.current
    shownRef.current = conversationId

    // We navigated here ourselves after creating the conversation for the message being
    // streamed right now: keep that stream and the messages on screen.
    if (conversationId && createdHereRef.current === conversationId) {
      createdHereRef.current = null
      return
    }
    setLoadError(null)
    if (!conversationId) {
      if (previous !== null) setMessages([]) // "New chat"
      return
    }
    setMsgLoading(true)
    setMessages([])
    const stillShown = () => shownRef.current === conversationId
    listMessages(conversationId)
      .then((ms) => stillShown() && setMessages(ms.map((m) => ({ ...m, stopped: m.status === 'stopped' }))))
      .catch((e) => stillShown() && setLoadError((e as Error).message))
      .finally(() => stillShown() && setMsgLoading(false))
  }, [conversationId])

  // Keep the newest message in view while streaming, unless the user scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const onScroll = () => {
    const el = scrollRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }

  const patch = (id: string, change: Partial<UIMessage> | ((m: UIMessage) => Partial<UIMessage>)) =>
    setMessages((ms) =>
      ms.map((m) => (m.id === id ? { ...m, ...(typeof change === 'function' ? change(m) : change) } : m)),
    )

  const send = useCallback(
    async (text: string) => {
      if (streaming) return
      stickToBottom.current = true
      const assistantId = tempId()
      setMessages((ms) => [
        ...ms,
        { id: tempId(), role: 'user', content: text, citations: [] },
        { id: assistantId, role: 'assistant', content: '', citations: [], pending: true, stage: 'understanding' },
      ])
      setStreaming(true)
      const ctrl = new AbortController()
      abortRef.current = ctrl

      try {
        let id = conversationId
        if (!id) {
          const conv = await createConversation()
          id = conv.id
          createdHereRef.current = id
          setConversations((cs) => [conv, ...cs])
          navigate(`/chat/${id}`)
        }
        await streamAnswer(
          id,
          text,
          (ev) => {
            if (ev.type === 'status') patch(assistantId, { stage: ev.stage })
            else if (ev.type === 'token') patch(assistantId, (m) => ({ content: m.content + ev.text }))
            else if (ev.type === 'done')
              // swap the temporary id for the saved message id (needed for feedback)
              patch(assistantId, {
                content: ev.answer,
                citations: ev.citations,
                pending: false,
                id: ev.message_id ?? assistantId,
              })
            else if (ev.type === 'error') patch(assistantId, { error: ev.message, pending: false })
          },
          ctrl.signal,
        )
        patch(assistantId, (m) =>
          m.pending ? { pending: false, error: 'The answer was interrupted. Please try again.' } : {},
        )
      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          patch(assistantId, { pending: false, stopped: true })
        } else {
          patch(assistantId, { pending: false, error: (e as Error).message })
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
        refreshConversations() // new title / ordering
      }
    },
    // patch is stable enough (uses functional setState)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [streaming, conversationId, navigate, refreshConversations],
  )

  // A question typed on the Home page arrives as ?q=… : send it once.
  const sentQuery = useRef(false)
  useEffect(() => {
    const q = params.get('q')?.trim()
    if (!q || sentQuery.current) return
    sentQuery.current = true
    setParams({}, { replace: true })
    void send(q)
  }, [params, setParams, send])

  const retry = (assistantId: string) => {
    const i = messages.findIndex((m) => m.id === assistantId)
    const question = messages[i - 1]?.role === 'user' ? messages[i - 1].content : null
    if (!question) return
    setMessages((ms) => ms.filter((_, j) => j !== i && j !== i - 1))
    void send(question)
  }

  const newChat = () => {
    abortRef.current?.abort()
    setDrawer(false)
    navigate('/chat')
  }

  const remove = async (c: Conversation) => {
    const ok = await confirm({
      title: 'Delete this conversation?',
      message: `“${c.title || 'New conversation'}” and its answers will be deleted. This can’t be undone.`,
      confirmLabel: 'Delete',
      tone: 'danger',
    })
    if (!ok) return
    // Remove it from the list straight away (the server also clears the assistant's memory,
    // which takes a second or two); put it back if the delete fails.
    const before = conversations
    setConversations((cs) => cs.filter((x) => x.id !== c.id))
    if (c.id === conversationId) {
      abortRef.current?.abort()
      navigate('/chat')
    }
    try {
      await deleteConversation(c.id)
      toast('Conversation deleted.')
    } catch (e) {
      setConversations(before)
      toast(`Couldn’t delete the conversation. ${(e as Error).message}`, 'error')
    }
  }

  const setFeedback = (messageId: string, value: 1 | -1 | null) =>
    patch(messageId, { feedback: value })

  const title = conversations.find((c) => c.id === conversationId)?.title
  const sidebar = (
    <Sidebar
      conversations={conversations}
      loading={convLoading}
      activeId={conversationId}
      onNew={newChat}
      onDelete={remove}
      onNavigate={() => {
        abortRef.current?.abort() // opening another conversation stops the current answer
        setDrawer(false)
      }}
    />
  )

  return (
    <div className="flex h-svh overflow-hidden bg-white">
      {/* Sidebar: fixed column on desktop, drawer on smaller screens */}
      <aside className="hidden w-72 shrink-0 lg:block">{sidebar}</aside>
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Conversations">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-navy/40" onClick={() => setDrawer(false)} />
          <div className="relative h-full w-72 max-w-[85vw] shadow-lift">
            {sidebar}
            <button
              type="button"
              onClick={() => setDrawer(false)}
              aria-label="Close menu"
              className="absolute top-4 right-3 grid size-9 place-items-center rounded-lg text-white/80 hover:bg-white/10"
            >
              <X size={20} />
            </button>
          </div>
        </div>
      )}

      <div className="relative flex min-w-0 flex-1 flex-col">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(ellipse_at_top,rgb(42_157_143/0.10),transparent_70%)]"
        />
        <header className="relative z-10 flex h-14 shrink-0 items-center gap-3 border-b border-navy/5 bg-white/80 px-4 backdrop-blur lg:px-6">
          <button
            type="button"
            onClick={() => setDrawer(true)}
            aria-label="Open conversations"
            className="grid size-9 place-items-center rounded-lg text-navy hover:bg-navy/5 lg:hidden"
          >
            <Menu size={20} />
          </button>
          <h1 className="truncate text-sm font-bold">{conversationId ? title || 'Conversation' : 'New conversation'}</h1>
        </header>

        <div ref={scrollRef} onScroll={onScroll} className="relative min-h-0 flex-1 overflow-y-auto">
          {msgLoading ? (
            <div className="grid h-full place-items-center">
              <Spinner label="Loading conversation" />
            </div>
          ) : loadError ? (
            <p className="mx-auto max-w-md px-6 py-24 text-center text-navy/70">
              This conversation couldn’t be loaded. {loadError}
            </p>
          ) : messages.length === 0 ? (
            <EmptyState name={user?.full_name ?? null} onPick={(q) => void send(q)} />
          ) : (
            <MessageList
              messages={messages}
              conversationId={conversationId}
              onRetry={retry}
              onFeedback={setFeedback}
            />
          )}
        </div>

        <div className="relative shrink-0 bg-linear-to-t from-white via-white to-white/0 pt-2 pb-4">
          <Composer onSend={(t) => void send(t)} onStop={() => abortRef.current?.abort()} streaming={streaming} />
        </div>
      </div>
    </div>
  )
}
