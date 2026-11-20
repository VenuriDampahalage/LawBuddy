/** Admin API: legislation documents. */

import { API_BASE, ApiError, apiFetch, tokenStore } from './api'
import type { Citation } from './chat'

export type DocStatus = 'pending' | 'parsing' | 'chunking' | 'embedding' | 'ready' | 'failed'

export type DocumentInfo = {
  id: string
  filename: string
  status: DocStatus
  error: string | null
  page_count: number | null
  created_at: string
  updated_at: string
  acts: number
  chunks: number
}

export type ActInfo = {
  id: string
  title: string
  kind: 'principal' | 'amendment' | 'special' | 'constitution'
  act_number: number | null
  year: number | null
  page_start: number | null
  page_end: number | null
  sections: number
}

export type DocumentDetail = DocumentInfo & { act_list: ActInfo[] }

export const IN_PROGRESS: DocStatus[] = ['pending', 'parsing', 'chunking', 'embedding']
export const MAX_UPLOAD_MB = 50

export const listDocuments = () => apiFetch<DocumentInfo[]>('/admin/documents')
export const getDocument = (id: string) => apiFetch<DocumentDetail>(`/admin/documents/${id}`)
export const reprocessDocument = (id: string) =>
  apiFetch<DocumentInfo>(`/admin/documents/${id}/reprocess`, { method: 'POST' })
export const deleteDocument = (id: string) =>
  apiFetch<void>(`/admin/documents/${id}`, { method: 'DELETE' })

/** Upload with progress (fetch can't report upload progress, XMLHttpRequest can). */
export function uploadDocument(
  file: File,
  onProgress: (fraction: number) => void,
): Promise<{ document: DocumentInfo; created: boolean }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/admin/documents`)
    xhr.setRequestHeader('Authorization', `Bearer ${tokenStore.get() ?? ''}`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onerror = () => reject(new ApiError(0, 'Upload failed. Check your connection and try again.'))
    xhr.onload = () => {
      let body: { detail?: unknown } & Record<string, unknown> = {}
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* not JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as unknown as { document: DocumentInfo; created: boolean })
      } else {
        const msg = typeof body.detail === 'string' ? body.detail : `Upload failed (${xhr.status})`
        reject(new ApiError(xhr.status, msg))
      }
    }
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

export const KIND_LABEL: Record<ActInfo['kind'], string> = {
  principal: 'Principal Act',
  amendment: 'Amendment',
  special: 'Special provisions',
  constitution: 'Constitution',
}

export const STEPS: { status: DocStatus; label: string }[] = [
  { status: 'pending', label: 'Queued' },
  { status: 'parsing', label: 'Reading PDF' },
  { status: 'chunking', label: 'Finding sections' },
  { status: 'embedding', label: 'Indexing' },
  { status: 'ready', label: 'Ready' },
]

/** "stored as 1a2b3c4d5e6f_Penal_Code.pdf" -> "Penal Code.pdf" */
export function displayName(filename: string): string {
  return filename.replace(/^[0-9a-f]{12}_/, '').replace(/_/g, ' ')
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

// ---- users -----------------------------------------------------------------------------

export type AdminUser = {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  role: 'user' | 'admin'
  is_active: boolean
  has_password: boolean
  google_linked: boolean
  created_at: string
  conversations: number
  last_active: string | null
}

export type UserFilter = 'all' | 'admins' | 'disabled'

export const listUsers = (q: string, filter: UserFilter, signal?: AbortSignal) =>
  apiFetch<AdminUser[]>(`/admin/users?${new URLSearchParams({ q, filter })}`, { signal })

export const updateUser = (id: string, change: { role?: 'user' | 'admin'; is_active?: boolean }) =>
  apiFetch<AdminUser>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(change) })

// ---- feedback --------------------------------------------------------------------------

export type FeedbackItem = {
  message_id: string
  conversation_id: string
  rating: 1 | -1
  question: string | null
  answer: string
  citations: Citation[]
  answered_at: string
  user_email: string
}

export type FeedbackRating = 'not_helpful' | 'helpful' | 'all'

export const listFeedback = (rating: FeedbackRating) =>
  apiFetch<{ helpful: number; not_helpful: number; items: FeedbackItem[] }>(
    `/admin/feedback?rating=${rating}`,
  )

// ---- amendments ------------------------------------------------------------------------

export type ProposalStatus = 'pending' | 'needs_attention' | 'approved' | 'rejected'

export type Proposal = {
  id: string
  status: ProposalStatus
  operation: string
  summary: string
  problem: string | null
  edited: boolean
  amendment_act: string
  amendment_year: number | null
  amendment_provision: string | null
  amendment_heading: string | null
  amendment_text: string
  target_act: string
  target_provision: string
  new_provision: string | null
  current_heading: string | null
  proposed_heading: string | null
  current_text: string
  proposed_text: string
  reviewed_at: string | null
  created_at: string
}

export type ProposalFilter = 'open' | 'approved' | 'rejected' | 'all'

export const listProposals = (filter: ProposalFilter) =>
  apiFetch<{ scanning: boolean; counts: Partial<Record<ProposalStatus, number>>; items: Proposal[] }>(
    `/admin/amendments?status_filter=${filter}`,
  )

export const scanAmendments = () => apiFetch<{ started: boolean }>('/admin/amendments/scan', { method: 'POST' })

export const proposalAction = (id: string, action: 'approve' | 'reject' | 'reopen' | 'revert') =>
  apiFetch<Proposal>(`/admin/amendments/${id}/${action}`, { method: 'POST' })

export const editProposal = (id: string, proposedText: string, proposedHeading: string | null) =>
  apiFetch<Proposal>(`/admin/amendments/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ proposed_text: proposedText, proposed_heading: proposedHeading }),
  })

export const OPERATION_LABEL: Record<string, string> = {
  substitute_words: 'Word change',
  replace: 'Replaced text',
  insert_after: 'Inserted text',
  insert_section: 'New section',
  repeal: 'Repeal',
  replace_heading: 'Heading change',
  multiple: 'Several changes',
  other: 'Other change',
}
