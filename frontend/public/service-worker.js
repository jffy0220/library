const CACHE_NAME = 'library-app-shell-v1'
const OFFLINE_URLS = ['/', '/index.html', '/manifest.webmanifest']
const DB_NAME = 'library-offline'
const STORE_NAME = 'snippet-queue'
const SYNC_TAG = 'sync-snippet-queue'

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME)
      await cache.addAll(OFFLINE_URLS)
      self.skipWaiting()
    })()
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys()
      await Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
      await processQueue()
      await self.clients.claim()
    })()
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  if (request.method === 'POST' && url.pathname === '/api/snippets') {
    event.respondWith(handleSnippetRequest(event))
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request))
    return
  }

  if (
    request.method === 'GET' &&
    url.origin === self.location.origin &&
    ['style', 'script', 'font', 'image'].includes(request.destination)
  ) {
    event.respondWith(cacheFirst(request))
    return
  }
})

self.addEventListener('sync', (event) => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(processQueue())
  }
})

self.addEventListener('message', (event) => {
  if (event?.data === 'processQueue') {
    event.waitUntil(processQueue())
  }
})

async function networkFirst(request) {
  try {
    const response = await fetch(request)
    const cache = await caches.open(CACHE_NAME)
    cache.put(request, response.clone())
    return response
  } catch (err) {
    const cache = await caches.open(CACHE_NAME)
    const cached = await cache.match(request)
    if (cached) return cached
    return cache.match('/index.html')
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  cache.put(request, response.clone())
  return response
}

async function handleSnippetRequest(event) {
  const { request } = event
  try {
    const networkResponse = await fetch(request.clone())
    if (!networkResponse.ok && networkResponse.status >= 500) {
      throw new Error('Server unavailable')
    }
    return networkResponse
  } catch (error) {
    const queuedResponse = await queueSnippetRequest(request)
    return queuedResponse
  }
}

function openQueueDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function queueSnippetRequest(request) {
  try {
    const db = await openQueueDb()
    const cloned = request.clone()
    let body = null
    try {
      body = await cloned.json()
    } catch (err) {
      body = null
    }
    const headers = {}
    request.headers.forEach((value, key) => {
      headers[key] = value
    })
    const record = {
      id: Date.now() + Math.random(),
      url: request.url,
      method: request.method,
      headers,
      body,
    }
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      tx.objectStore(STORE_NAME).put(record)
      tx.oncomplete = resolve
      tx.onerror = () => reject(tx.error)
    })
    registerSync()
  } catch (err) {
    console.error('Failed to queue snippet request', err)
  }

  return new Response(
    JSON.stringify({ queued: true, message: 'Snippet saved offline. It will sync when you reconnect.' }),
    {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    }
  )
}

async function getQueuedRequests() {
  const db = await openQueueDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const request = store.getAll()
    request.onsuccess = () => resolve(request.result || [])
    request.onerror = () => reject(request.error)
  })
}

async function removeQueuedRequest(id) {
  const db = await openQueueDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).delete(id)
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
}

async function processQueue() {
  try {
    const pending = await getQueuedRequests()
    if (!pending.length) {
      return
    }
    let successCount = 0
    for (const item of pending) {
      try {
        const response = await fetch(item.url, {
          method: item.method,
          headers: item.headers,
          body: item.body ? JSON.stringify(item.body) : undefined,
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Failed with status ${response.status}`)
        }
        await removeQueuedRequest(item.id)
        successCount += 1
      } catch (err) {
        const isOffline = err instanceof TypeError
        if (!isOffline) {
          await removeQueuedRequest(item.id)
          await notifyClients({
            type: 'SNIPPET_SYNC_ERROR',
            message: 'A snippet could not be synced.',
          })
        } else {
          break
        }
      }
    }
    if (successCount > 0) {
      const message =
        successCount === 1
          ? 'Offline snippet synced.'
          : `${successCount} offline snippets synced.`
      await notifyClients({ type: 'SNIPPET_SYNC_COMPLETE', message })
    }
  } catch (err) {
    console.error('Failed to process snippet queue', err)
  }
}

async function notifyClients(message) {
  const clients = await self.clients.matchAll({ includeUncontrolled: true })
  for (const client of clients) {
    client.postMessage(message)
  }
}

async function registerSync() {
  if (!self.registration.sync) return
  try {
    await self.registration.sync.register(SYNC_TAG)
  } catch (err) {
    console.warn('Background sync registration failed', err)
    // Fallback: attempt to process queue soon
    setTimeout(() => {
      processQueue()
    }, 10000)
  }
}