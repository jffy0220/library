import { useCallback, useEffect, useRef, useState } from 'react'
import { getUnreadNotificationCount, listNotifications } from '../api'

export function useNotifications(options = {}) {
  const { pollIntervalMs = 60000, enabled = true, onNewNotification } = options
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const intervalRef = useRef(null)
  const controllerRef = useRef(null)
  const latestControllerRef = useRef(null)
  const isMountedRef = useRef(false)
  const lastKnownCreatedAtRef = useRef(null)
  const previousUnreadRef = useRef(null)

  const normalizeLatestNotification = useCallback((item) => {
    if (!item || typeof item !== 'object') return null
    const createdAt = item.createdAt ?? item.created_at ?? null
    const actorName =
      item.actorDisplayName ??
      item.actor_display_name ??
      item.actorName ??
      item.actor_name ??
      item.actorUsername ??
      item.actor_username ??
      item.actor?.displayName ??
      item.actor?.name ??
      item.actor?.username ??
      null

    return {
      id: item.id ?? null,
      createdAt,
      actorName,
      type: item.type ?? null
    }
  }, [])

  const fetchLatestNotification = useCallback(async () => {
    if (!enabled) return null

    if (latestControllerRef.current) {
      latestControllerRef.current.abort()
    }
    const controller = new AbortController()
    latestControllerRef.current = controller

    try {
      const data = await listNotifications({ limit: 1 }, { signal: controller.signal })
      if (!isMountedRef.current || controller.signal.aborted) return null
      const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []
      const latest = items.length > 0 ? normalizeLatestNotification(items[0]) : null
      if (latest?.createdAt) {
        lastKnownCreatedAtRef.current = lastKnownCreatedAtRef.current ?? latest.createdAt
      }
      return latest
    } catch (err) {
      if (!isMountedRef.current || controller.signal.aborted) return null
      return null
    }
  }, [enabled, normalizeLatestNotification])

  const isTimestampAfter = useCallback((a, b) => {
    if (!a || !b) return false
    const first = new Date(a)
    const second = new Date(b)
    if (Number.isNaN(first.getTime()) || Number.isNaN(second.getTime())) return false
    return first.getTime() > second.getTime()
  }, [])

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
      const newUnread = typeof data?.unread_count === 'number' ? data.unread_count : 0
      setUnreadCount(newUnread)
      const previousUnread = previousUnreadRef.current
      previousUnreadRef.current = newUnread

      if (
        typeof previousUnread === 'number' &&
        newUnread > previousUnread &&
        typeof onNewNotification === 'function'
      ) {
        const latest = await fetchLatestNotification()
        if (!isMountedRef.current || !latest?.createdAt) return
        if (lastKnownCreatedAtRef.current) {
          if (isTimestampAfter(latest.createdAt, lastKnownCreatedAtRef.current)) {
            lastKnownCreatedAtRef.current = latest.createdAt
            onNewNotification(latest)
          }
        } else {
          lastKnownCreatedAtRef.current = latest.createdAt
        }
      }
      setError(null)
    } catch (err) {
      if (!isMountedRef.current || controller.signal.aborted) return
      setError(err)
    } finally {
      if (!isMountedRef.current || controller.signal.aborted) return
      setLoading(false)
    }
  }, [
    enabled,
    fetchLatestNotification,
    isTimestampAfter,
    onNewNotification
  ])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      setLoading(false)
      setUnreadCount(0)
      setError(null)
      previousUnreadRef.current = 0
      lastKnownCreatedAtRef.current = null
      if (controllerRef.current) {
        controllerRef.current.abort()
        controllerRef.current = null
      }
      if (latestControllerRef.current) {
        latestControllerRef.current.abort()
        latestControllerRef.current = null
      }
      return () => {
        isMountedRef.current = false
      }
    }

    fetchUnreadCount()
    fetchLatestNotification()

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
      if (latestControllerRef.current) {
        latestControllerRef.current.abort()
        latestControllerRef.current = null
      }
    }
  }, [enabled, fetchLatestNotification, fetchUnreadCount, pollIntervalMs])

  const refresh = useCallback(() => {
    if (!enabled) return Promise.resolve()
    return fetchUnreadCount()
  }, [enabled, fetchUnreadCount])

  return { unreadCount, loading, error, refresh }
}