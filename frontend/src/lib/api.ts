/** API client. Every backend request goes through API_BASE. */

/**
 * The backend's address. It is set only in VITE_API_URL: frontend/.env locally, the host's
 * environment variables when deployed. The backend must list this site in CORS_ORIGINS.
 */
const API_ORIGIN = ((import.meta.env.VITE_API_URL as string | undefined) ?? '')
  .trim()
  .replace(/\/+$/, '') // a trailing "/" is fine
  .replace(/\/api$/, '') // so is a value that already ends in /api

if (!API_ORIGIN) {
  console.error(
    'VITE_API_URL is not set, so LawBuddy cannot reach its backend. ' +
      'Add it to frontend/.env (or the host’s environment variables) and restart / redeploy.',
  )
}

export const API_BASE = `${API_ORIGIN}/api`

/** Full URL for a backend path that already starts with /api (e.g. a link the server returned). */
export const backendUrl = (path: string) => `${API_ORIGIN}${path}`

const TOKEN_KEY = 'lawbuddy.token'

export type User = {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  role: 'user' | 'admin'
  has_password: boolean
  google_linked: boolean
  created_at: string
}

export type Law = {
  title: string
  kind: 'principal' | 'amendment' | 'special' | 'constitution'
  act_number: number | null
  year: number | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set: (t: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, t)
    } catch {
      /* storage unavailable (private mode): session-only login */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

/** Turn FastAPI error bodies ({detail: "..."} or validation lists) into one readable message. */
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      const first = body.detail[0]
      const field = first.loc?.at(-1)
      return field ? `${field}: ${first.msg}` : first.msg
    }
  } catch {
    /* not JSON */
  }
  return res.status >= 500 ? 'The server had a problem. Please try again.' : `Request failed (${res.status})`
}

/** Called when the server rejects our token, so the app can log out everywhere. */
let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams)) {
    headers.set('Content-Type', 'application/json')
  }
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }
  if (res.status === 401 && token) onUnauthorized()
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---- endpoints ---------------------------------------------------------------------

export const getLaws = (signal?: AbortSignal) => apiFetch<Law[]>('/laws', { signal })

export const getMe = () => apiFetch<User>('/auth/me')

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email, password })
  return apiFetch<{ access_token: string; user: User }>('/auth/login', { method: 'POST', body })
}

export const register = (email: string, password: string, fullName: string) =>
  apiFetch<User>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name: fullName || null }),
  })

export const getAuthConfig = () => apiFetch<{ google_client_id: string | null }>('/auth/config')

export const googleSignIn = (credential: string) =>
  apiFetch<{ access_token: string; user: User }>('/auth/google', {
    method: 'POST',
    body: JSON.stringify({ credential }),
  })

export const updateProfile = (fullName: string) =>
  apiFetch<User>('/auth/me', { method: 'PATCH', body: JSON.stringify({ full_name: fullName }) })

export const changePassword = (currentPassword: string | null, newPassword: string) =>
  apiFetch<void>('/auth/me/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })

export const deleteAccount = (confirmEmail: string) =>
  apiFetch<void>('/auth/me', { method: 'DELETE', body: JSON.stringify({ confirm_email: confirmEmail }) })
