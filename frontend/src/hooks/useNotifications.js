import { useCallback, useEffect, useRef, useState } from 'react'
import { getUnreadNotificationCount } from '../api'

export function useNotifications(options = {}) {
  const { pollIntervalMs = 60000, enabled = true } = options
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const intervalRef = useRef(null)
  const controllerRef = useRef(null)
  const isMountedRef = useRef(false)

  const fetchUnreadCount = useCallback(async () => {
    if (!enabled) return

    if (controllerRef.current) {
      controllerRef.current.abort()
    }
    const controller = new AbortController()
    controllerRef.current = controller

    try {
      const data = await getUnreadNotificationCount({ signal: controller.signal })
      if (!isMountedRef.current || controller.signal.aborted) return
      setUnreadCount(typeof data?.unread_count === 'number' ? data.unread_count : 0)
      setError(null)
    } catch (err) {
      if (!isMountedRef.current || controller.signal.aborted) return
      setError(err)
    } finally {
      if (!isMountedRef.current || controller.signal.aborted) return
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      setLoading(false)
      setUnreadCount(0)
      setError(null)
      if (controllerRef.current) {
        controllerRef.current.abort()
        controllerRef.current = null
      }
      return () => {
        isMountedRef.current = false
      }
    }

    fetchUnreadCount()

    if (pollIntervalMs > 0) {
      intervalRef.current = setInterval(fetchUnreadCount, pollIntervalMs)
    }

    return () => {
      isMountedRef.current = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      if (controllerRef.current) {
        controllerRef.current.abort()
        controllerRef.current = null
      }
    }
  }, [enabled, fetchUnreadCount, pollIntervalMs])

  const refresh = useCallback(() => {
    if (!enabled) return Promise.resolve()
    return fetchUnreadCount()
  }, [enabled, fetchUnreadCount])

  return { unreadCount, loading, error, refresh }
}