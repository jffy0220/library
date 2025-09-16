import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { fetchCurrentUser, login as apiLogin, logout as apiLogout, setUnauthorizedHandler } from './api'

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

  const login = async (username, password) => {
    try {
      const data = await apiLogin({ username, password })
      setUser(data)
      return data
    } catch (err) {
      setUser(null)
      throw err
    }
  }

  const logout = async () => {
    try {
      await apiLogout()
    } finally {
      setUser(null)
    }
  }

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}