import { createContext, useContext } from 'react'

import type { User } from './api'

export type AuthState = {
  user: User | null
  /** true while we check a saved token on page load */
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  /** Exchange a Google ID token (from the Google button) for a LawBuddy session. */
  loginWithGoogle: (credential: string) => Promise<User>
  register: (email: string, password: string, fullName: string) => Promise<User>
  logout: () => void
  /** Replace the signed-in user after a profile change. */
  updateUser: (user: User) => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

/** Only allow redirects to paths inside this site (prevents open-redirects via ?next=). */
export function safeNext(next: string | null, fallback = '/chat'): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) {
    return fallback
  }
  return next
}

/** "Kasun Perera" -> "KP"; "nimal@example.com" -> "N" */
export function initials(user: User): string {
  const source = user.full_name?.trim() || user.email
  const parts = source.split(/[\s@._-]+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (user.full_name ? (parts[1]?.[0] ?? '') : '')).toUpperCase()
}
