import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import * as api from '../lib/api'
import { AuthContext } from '../lib/auth'

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null)
  const [loading, setLoading] = useState(() => api.tokenStore.get() !== null)

  const logout = useCallback(() => {
    api.tokenStore.clear()
    setUser(null)
  }, [])

  // Restore the session from a saved token.
  useEffect(() => {
    api.setUnauthorizedHandler(logout)
    if (!api.tokenStore.get()) return
    api
      .getMe()
      .then(setUser)
      .catch(() => api.tokenStore.clear())
      .finally(() => setLoading(false))
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password)
    api.tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const loginWithGoogle = useCallback(async (credential: string) => {
    const res = await api.googleSignIn(credential)
    api.tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      await api.register(email, password, fullName)
      return login(email, password)
    },
    [login],
  )

  const value = useMemo(
    () => ({ user, loading, login, loginWithGoogle, register, logout, updateUser: setUser }),
    [user, loading, login, loginWithGoogle, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
