import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { fetchCurrentUser, login as apiLogin, logout as apiLogout, setUnauthorizedHandler } from './api'
import { capture, setUserId } from './lib/analytics'

const AuthContext = createContext({
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {}
})

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    let ignore = false
    ;(async () => {
      try {
        const data = await fetchCurrentUser()
        if (!ignore) setUser(data)
      } catch {
        if (!ignore) setUser(null)
      } finally {
        if (!ignore) setLoading(false)
      }
    })()
    return () => {
      ignore = true
      setUnauthorizedHandler(null)
    }
  }, [])

  useEffect(() => {
    setUserId(user?.id ? String(user.id) : null)
  }, [user])

  const login = async (username, password) => {
    try {
      const data = await apiLogin({ username, password })
      setUser(data)
      setUserId(data?.id ? String(data.id) : null)
      capture({ event: 'user_logged_in', user_id: data?.id ? String(data.id) : undefined })
      return data
    } catch (err) {
      setUser(null)
      setUserId(null)
      throw err
    }
  }

  const logout = async () => {
    const currentId = user?.id ? String(user.id) : undefined
    try {
      await apiLogout()
    } finally {
      capture({ event: 'user_logged_out', user_id: currentId })
      setUserId(null)
      setUser(null)
    }
  }

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}