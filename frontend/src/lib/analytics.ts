// Vite injects env vars on import.meta.env, but our TS config doesn't ship its types.
// Cast import.meta to any to avoid relying on global type augmentation.
const VITE_ENV = ((import.meta as any) && (import.meta as any).env) || {}
const ANALYTICS_ENABLED = VITE_ENV.VITE_ANALYTICS_ENABLED === 'true'
const APP_VERSION = VITE_ENV.VITE_APP_VERSION

const FLUSH_INTERVAL = 2500
const ANON_ID_KEY = 'analytics.anonymous_id'
const SESSION_ID_KEY = 'analytics.session_id'

type Primitive = string | number | boolean | null

export interface CaptureEvent {
  event: string
  user_id?: string
  duration_ms?: number
  props?: Record<string, any>
  context?: Record<string, any>
}

interface AnalyticsEventPayload extends CaptureEvent {
  ts: string
  anonymous_id: string
  session_id: string
  route: string | undefined
}

const queue: AnalyticsEventPayload[] = []
let flushTimer: number | null = null
let flushing = false
let currentUserId: string | null = null

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return Math.random().toString(36).slice(2)
}

function readStorage(key: string, storage: Storage): string | null {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string, storage: Storage): void {
  try {
    storage.setItem(key, value)
  } catch {
    /* swallow */
  }
}

function ensureAnonymousId(): string {
  if (typeof window === 'undefined') return 'server'
  const storage = window.localStorage
  let existing = storage ? readStorage(ANON_ID_KEY, storage) : null
  if (!existing) {
    existing = generateId()
    if (storage) writeStorage(ANON_ID_KEY, existing, storage)
  }
  return existing
}

function ensureSessionId(): string {
  if (typeof window === 'undefined') return 'server'
  const storage = window.sessionStorage
  let existing = storage ? readStorage(SESSION_ID_KEY, storage) : null
  if (!existing) {
    existing = generateId()
    if (storage) writeStorage(SESSION_ID_KEY, existing, storage)
  }
  return existing
}

function sanitizePayload<T extends Record<string, any>>(payload: T): T {
  const clean: Record<string, any> = {}
  Object.entries(payload).forEach(([key, value]) => {
    if (value === undefined) return
    clean[key] = value
  })
  return clean as T
}

function scheduleFlush(): void {
  if (!ANALYTICS_ENABLED) return
  if (typeof window === 'undefined') return
  if (flushTimer != null) return
  flushTimer = window.setTimeout(() => {
    void flushQueue()
  }, FLUSH_INTERVAL)
}

interface FlushOptions {
  useBeacon?: boolean
}

async function flushQueue(options: FlushOptions = {}): Promise<void> {
  if (!ANALYTICS_ENABLED) return
  if (flushing) return
  if (queue.length === 0) return
  if (typeof window !== 'undefined' && flushTimer != null) {
    window.clearTimeout(flushTimer)
    flushTimer = null
  }
  flushing = true
  const events = queue.splice(0, queue.length)
  const payload = JSON.stringify({ events })
  const endpoint = '/analytics/collect'

  if (options.useBeacon && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    const blob = new Blob([payload], { type: 'application/json' })
    const sent = navigator.sendBeacon(endpoint, blob)
    if (sent) {
      flushing = false
      return
    }
  }

  try {
    await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: options.useBeacon === true
    })
  } catch (error) {
    if (!options.useBeacon) {
      queue.unshift(...events)
      scheduleFlush()
    }
  } finally {
    flushing = false
  }
}

export function capture(event: CaptureEvent): void {
  if (!ANALYTICS_ENABLED) return
  if (!event?.event) return
  const now = new Date().toISOString()
  const anonymousId = ensureAnonymousId()
  const sessionId = ensureSessionId()
  const route = typeof window !== 'undefined' ? window.location?.pathname : undefined
  const props = sanitizePayload({ ...(event.props || {}) })
  const context = sanitizePayload({ ...(event.context || {}) })
  if (APP_VERSION && context.app_version == null) {
    context.app_version = APP_VERSION
  }
  if (context.source == null) {
    context.source = 'web'
  }
  const payload: AnalyticsEventPayload = {
    event: event.event,
    ts: now,
    anonymous_id: anonymousId,
    session_id: sessionId,
    route,
    user_id: event.user_id ?? currentUserId ?? undefined,
    duration_ms: event.duration_ms,
    props,
    context
  }
  queue.push(payload)
  scheduleFlush()
}

export function setUserId(userId: string | null | undefined): void {
  if (!ANALYTICS_ENABLED) return
  currentUserId = userId ?? null
}

export function trackPageView(): void {
  capture({ event: 'page_view' })
}

export function initWebVitals(): void {
  if (!ANALYTICS_ENABLED) return
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  if (typeof PerformanceObserver === 'undefined') return

  let clsValue = 0
  let clsReported = false
  let lcpValue = 0
  let lcpReported = false
  let inpValue = 0
  let inpReported = false

  const reportCLS = () => {
    if (clsReported) return
    clsReported = true
    capture({
      event: 'web_vital',
      props: {
        name: 'CLS',
        value: Number(clsValue.toFixed(4))
      }
    })
  }

  const reportLCP = () => {
    if (lcpReported || lcpValue <= 0) return
    lcpReported = true
    capture({
      event: 'web_vital',
      props: {
        name: 'LCP',
        value: Math.round(lcpValue)
      }
    })
  }

  const reportINP = () => {
    if (inpReported || inpValue <= 0) return
    inpReported = true
    capture({
      event: 'web_vital',
      props: {
        name: 'INP',
        value: Math.round(inpValue)
      }
    })
  }

  try {
    const clsObserver = new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as PerformanceEntry[]) {
        const shift = entry as PerformanceEntry & { value?: number; hadRecentInput?: boolean }
        if (shift && shift.value && !shift.hadRecentInput) {
          clsValue += shift.value
        }
      }
    })
    clsObserver.observe({ type: 'layout-shift', buffered: true } as PerformanceObserverInit)
    document.addEventListener(
      'visibilitychange',
      () => {
        if (document.visibilityState === 'hidden') {
          clsObserver.disconnect()
          reportCLS()
        }
      },
      { once: true }
    )
    window.addEventListener(
      'pagehide',
      () => {
        clsObserver.disconnect()
        reportCLS()
      },
      { once: true }
    )
  } catch {
    /* ignore */
  }

  try {
    const lcpObserver = new PerformanceObserver((list) => {
      const entries = list.getEntries()
      const last = entries[entries.length - 1] as PerformanceEntry & { renderTime?: number; loadTime?: number }
      if (!last) return
      const value = last.renderTime || last.loadTime || last.startTime
      if (typeof value === 'number') {
        lcpValue = value
      }
    })
    lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true } as PerformanceObserverInit)
    const finalizeLCP = () => {
      lcpObserver.disconnect()
      reportLCP()
    }
    document.addEventListener(
      'visibilitychange',
      () => {
        if (document.visibilityState === 'hidden') {
          finalizeLCP()
        }
      },
      { once: true }
    )
    window.addEventListener('pagehide', finalizeLCP, { once: true })
  } catch {
    /* ignore */
  }

  const setupINPObserver = () => {
    try {
      const inpObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries() as PerformanceEntry[]) {
          const eventEntry = entry as PerformanceEntry & { interactionId?: number; duration?: number }
          if (eventEntry?.duration && (eventEntry.interactionId || eventEntry.duration > inpValue)) {
            inpValue = Math.max(inpValue, eventEntry.duration)
          }
        }
      })
      inpObserver.observe({ type: 'event', buffered: true } as PerformanceObserverInit)
      const finalizeINP = () => {
        inpObserver.disconnect()
        reportINP()
      }
      document.addEventListener(
        'visibilitychange',
        () => {
          if (document.visibilityState === 'hidden') {
            finalizeINP()
          }
        },
        { once: true }
      )
      window.addEventListener('pagehide', finalizeINP, { once: true })
      return true
    } catch {
      return false
    }
  }

  if (!setupINPObserver()) {
    try {
      const firstInputObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries()
        const entry = entries[0] as PerformanceEntry & { processingStart?: number; startTime?: number }
        if (!entry) return
        const duration = entry.processingStart && entry.startTime ? entry.processingStart - entry.startTime : entry.duration
        if (typeof duration === 'number') {
          inpValue = Math.max(inpValue, duration)
        }
      })
      firstInputObserver.observe({ type: 'first-input', buffered: true } as PerformanceObserverInit)
      const finalizeFirstInput = () => {
        firstInputObserver.disconnect()
        reportINP()
      }
      document.addEventListener(
        'visibilitychange',
        () => {
          if (document.visibilityState === 'hidden') {
            finalizeFirstInput()
          }
        },
        { once: true }
      )
      window.addEventListener('pagehide', finalizeFirstInput, { once: true })
    } catch {
      /* ignore */
    }
  }
}

if (ANALYTICS_ENABLED && typeof window !== 'undefined') {
  const flushWithBeacon = () => {
    void flushQueue({ useBeacon: true })
  }
  window.addEventListener('pagehide', flushWithBeacon)
  window.addEventListener('beforeunload', flushWithBeacon)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flushWithBeacon()
    }
  })

  window.addEventListener('error', (event) => {
    const message = event.message || (event.error && event.error.message)
    if (!message) return
    const stack = event.error && event.error.stack ? String(event.error.stack).slice(0, 2000) : undefined
    capture({
      event: 'frontend_error',
      props: sanitizePayload({
        message,
        stack,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
      })
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    let message: Primitive = 'Unhandled rejection'
    let stack: string | undefined
    const reason: any = event.reason
    if (reason) {
      if (typeof reason === 'string') {
        message = reason
      } else if (reason?.message) {
        message = reason.message
      }
      if (reason?.stack) {
        stack = String(reason.stack).slice(0, 2000)
      }
    }
    capture({
      event: 'frontend_error',
      props: sanitizePayload({
        message,
        stack
      })
    })
  })
}

export const analytics = {
  capture,
  trackPageView,
  initWebVitals,
  setUserId
}

export default analytics
