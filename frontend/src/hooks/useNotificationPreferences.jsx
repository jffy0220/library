import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  getNotificationPreferences,
  updateNotificationPreferences
} from '../api'
import { useAuth } from '../auth'

const NotificationPreferencesContext = createContext({
  preferences: null,
  loading: false,
  error: null,
  updating: false,
  refresh: async () => {},
  update: async () => {}
})

export function NotificationPreferencesProvider({ children }) {
  const { user } = useAuth()
  const [preferences, setPreferences] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [updating, setUpdating] = useState(false)

  const fetchPreferences = useCallback(async () => {
    if (!user) {
      setPreferences(null)
      setError(null)
      setLoading(false)
      return null
    }

    setLoading(true)
    try {
      const data = await getNotificationPreferences()
      setPreferences(data ?? null)
      setError(null)
      return data ?? null
    } catch (err) {
      setPreferences(null)
      setError(err)
      throw err
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    let ignore = false
    if (!user) {
      setPreferences(null)
      setError(null)
      setLoading(false)
      return () => {
        ignore = true
      }
    }

    setLoading(true)
    getNotificationPreferences()
      .then((data) => {
        if (ignore) return
        setPreferences(data ?? null)
        setError(null)
      })
      .catch((err) => {
        if (ignore) return
        setPreferences(null)
        setError(err)
      })
      .finally(() => {
        if (ignore) return
        setLoading(false)
      })

    return () => {
      ignore = true
    }
  }, [user])

  const savePreferences = useCallback(
    async (updates) => {
      if (!user) {
        const errorMessage = new Error('Not authenticated')
        setError(errorMessage)
        throw errorMessage
      }

      setUpdating(true)
      try {
        const data = await updateNotificationPreferences(updates)
        setPreferences(data ?? null)
        setError(null)
        return data ?? null
      } catch (err) {
        setError(err)
        throw err
      } finally {
        setUpdating(false)
      }
    },
    [user]
  )

  const value = useMemo(
    () => ({
      preferences,
      loading,
      error,
      updating,
      refresh: fetchPreferences,
      update: savePreferences
    }),
    [preferences, loading, error, updating, fetchPreferences, savePreferences]
  )

  return (
    <NotificationPreferencesContext.Provider value={value}>
      {children}
    </NotificationPreferencesContext.Provider>
  )
}

export function useNotificationPreferences() {
  return useContext(NotificationPreferencesContext)
}