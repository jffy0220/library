import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react'
import {
  listDirectMessageThreadMessages,
  listDirectMessageThreads,
  markDirectMessageThreadRead,
  sendDirectMessage,
  startDirectMessage
} from '../api'
import { useAuth } from '../auth'

const MAX_MESSAGE_LENGTH = 280

function sortThreadsByActivity(threads = []) {
  return [...threads].sort((a, b) => {
    const getTime = (thread) => {
      const candidate =
        thread?.lastMessage?.createdAt ??
        thread?.lastMessageAt ??
        thread?.createdAt
      if (!candidate) return 0
      const date = new Date(candidate)
      return Number.isNaN(date.getTime()) ? 0 : date.getTime()
    }
    return getTime(b) - getTime(a)
  })
}

function formatRelativeTime(value) {
  if (!value) return ''
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const now = Date.now()
    const diffMs = date.getTime() - now
    const absDiff = Math.abs(diffMs)
    const units = [
      ['year', 1000 * 60 * 60 * 24 * 365],
      ['month', 1000 * 60 * 60 * 24 * 30],
      ['week', 1000 * 60 * 60 * 24 * 7],
      ['day', 1000 * 60 * 60 * 24],
      ['hour', 1000 * 60 * 60],
      ['minute', 1000 * 60],
      ['second', 1000]
    ]
    for (const [unit, ms] of units) {
      if (absDiff >= ms || unit === 'second') {
        const valueRounded = Math.round(diffMs / ms)
        const formatter = new Intl.RelativeTimeFormat(undefined, {
          numeric: 'auto'
        })
        return formatter.format(valueRounded, unit)
      }
    }
    return ''
  } catch (err) {
    return ''
  }
}

function getErrorMessage(error) {
  if (!error) return ''
  if (error?.response?.data?.detail) return error.response.data.detail
  if (error?.message) return error.message
  return 'Something went wrong. Please try again.'
}

export default function MessagesPage() {
  const { user } = useAuth()
  const [threads, setThreads] = useState([])
  const [threadsLoading, setThreadsLoading] = useState(true)
  const [threadsError, setThreadsError] = useState(null)
  const [selectedThreadId, setSelectedThreadId] = useState(null)
  const [messageState, setMessageState] = useState({})
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [activeThreadError, setActiveThreadError] = useState(null)
  const [composerValue, setComposerValue] = useState('')
  const [sending, setSending] = useState(false)
  const [usernameInput, setUsernameInput] = useState('')
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState(null)
  const messagesEndRef = useRef(null)

  const refreshThreads = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setThreadsLoading(true)
    }
    try {
      const data = await listDirectMessageThreads()
      const items = Array.isArray(data?.threads) ? data.threads : []
      setThreads(sortThreadsByActivity(items))
      setThreadsError(null)
      return items
    } catch (err) {
      if (!silent) {
        setThreadsError(err)
      }
      throw err
    } finally {
      if (!silent) {
        setThreadsLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    let isMounted = true
    refreshThreads()
      .then((items) => {
        if (!isMounted) return
        setSelectedThreadId((current) => {
          if (current) return current
          return items && items.length > 0 ? items[0].id : null
        })
      })
      .catch(() => {})
    return () => {
      isMounted = false
    }
  }, [refreshThreads])

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) || null,
    [threads, selectedThreadId]
  )

  const activeState = messageState[selectedThreadId] || {
    messages: [],
    nextCursor: null,
    hasMore: false
  }
  const activeMessages = activeState.messages || []
  const activeHasMore = Boolean(activeState.hasMore)
  const activeCursor = activeState.nextCursor || null

  const markThreadAsRead = useCallback(async (threadId) => {
    if (!threadId) return
    try {
      const data = await markDirectMessageThreadRead(threadId)
      const unreadCount = typeof data?.unreadCount === 'number' ? data.unreadCount : 0
      setThreads((prev) =>
        prev.map((thread) =>
          thread.id === threadId ? { ...thread, unreadCount } : thread
        )
      )
    } catch (err) {
      // Ignore read errors so the user can continue messaging
    }
  }, [])

  const loadMessages = useCallback(
    async (threadId, { cursor, extend = false } = {}) => {
      if (!threadId) return
      setMessagesLoading(true)
      if (!extend) {
        setActiveThreadError(null)
      }
      try {
        const data = await listDirectMessageThreadMessages(threadId, {
          cursor,
          limit: 30
        })
        const fetchedMessages = Array.isArray(data?.messages) ? data.messages : []
        setMessageState((prev) => {
          const current = prev[threadId] || {
            messages: [],
            nextCursor: null,
            hasMore: false
          }
          let combined
          if (extend) {
            const existingIds = new Set(current.messages.map((msg) => msg.id))
            const filtered = fetchedMessages.filter((msg) => !existingIds.has(msg.id))
            combined = [...filtered, ...current.messages]
          } else {
            combined = fetchedMessages
          }
          return {
            ...prev,
            [threadId]: {
              messages: combined,
              nextCursor: data?.nextCursor ?? null,
              hasMore: Boolean(data?.hasMore)
            }
          }
        })
        if (!extend) {
          await markThreadAsRead(threadId)
        }
      } catch (err) {
        setActiveThreadError(err)
      } finally {
        setMessagesLoading(false)
      }
    },
    [markThreadAsRead]
  )

  const handleSelectThread = useCallback((threadId) => {
    setSelectedThreadId(threadId)
  }, [])

  useEffect(() => {
    if (!selectedThreadId) return
    const state = messageState[selectedThreadId]
    if (!state) {
      loadMessages(selectedThreadId)
      return
    }
    const thread = threads.find((item) => item.id === selectedThreadId)
    if (thread && thread.unreadCount > 0) {
      markThreadAsRead(selectedThreadId)
    }
  }, [selectedThreadId, messageState, loadMessages, markThreadAsRead, threads])

  useEffect(() => {
    if (activeMessages.length === 0) return
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [activeMessages, selectedThreadId])

  const handleLoadOlder = useCallback(() => {
    if (!selectedThreadId || !activeCursor) return
    loadMessages(selectedThreadId, { cursor: activeCursor, extend: true })
  }, [activeCursor, loadMessages, selectedThreadId])

  const handleSendMessage = useCallback(async () => {
    if (!selectedThreadId) return
    const text = composerValue.trim()
    if (!text) return
    setSending(true)
    setActiveThreadError(null)
    try {
      const data = await sendDirectMessage(selectedThreadId, { body: text })
      const message = data?.message
      const thread = data?.thread
      setComposerValue('')
      if (message) {
        setMessageState((prev) => {
          const current = prev[selectedThreadId] || {
            messages: [],
            nextCursor: null,
            hasMore: false
          }
          const existingIds = new Set(current.messages.map((item) => item.id))
          let nextMessages
          if (existingIds.has(message.id)) {
            nextMessages = current.messages.map((item) =>
              item.id === message.id ? message : item
            )
          } else {
            nextMessages = [...current.messages, message]
          }
          return {
            ...prev,
            [selectedThreadId]: {
              ...current,
              messages: nextMessages
            }
          }
        })
      }
      if (thread) {
        setThreads((prev) => {
          const existingIndex = prev.findIndex((item) => item.id === thread.id)
          if (existingIndex >= 0) {
            const updated = [...prev]
            updated[existingIndex] = thread
            return sortThreadsByActivity(updated)
          }
          return sortThreadsByActivity([thread, ...prev])
        })
      }
      await refreshThreads({ silent: true }).catch(() => {})
    } catch (err) {
      setActiveThreadError(err)
    } finally {
      setSending(false)
    }
  }, [composerValue, refreshThreads, selectedThreadId])

  const handleComposerSubmit = useCallback(
    (event) => {
      event.preventDefault()
      handleSendMessage()
    },
    [handleSendMessage]
  )

  const handleComposerKeyDown = useCallback(
    (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault()
        handleSendMessage()
      }
    },
    [handleSendMessage]
  )

  const handleStartConversation = useCallback(
    async (event) => {
      event.preventDefault()
      const username = usernameInput.trim()
      if (!username) {
        setStartError(new Error('Please enter a username'))
        return
      }
      setStarting(true)
      setStartError(null)
      try {
        const data = await startDirectMessage({ username })
        const thread = data?.thread
        setUsernameInput('')
        if (thread) {
          setThreads((prev) => {
            const existingIndex = prev.findIndex((item) => item.id === thread.id)
            if (existingIndex >= 0) {
              const updated = [...prev]
              updated[existingIndex] = thread
              return sortThreadsByActivity(updated)
            }
            return sortThreadsByActivity([thread, ...prev])
          })
          setMessageState((prev) => {
            const next = { ...prev }
            delete next[thread.id]
            return next
          })
          setSelectedThreadId(thread.id)
          await loadMessages(thread.id)
        }
        await refreshThreads({ silent: true }).catch(() => {})
      } catch (err) {
        setStartError(err)
      } finally {
        setStarting(false)
      }
    },
    [loadMessages, refreshThreads, usernameInput]
  )

  const remainingChars = Math.max(0, MAX_MESSAGE_LENGTH - composerValue.length)
  const composerDisabled = !selectedThreadId || sending
  const canSend = !composerDisabled && composerValue.trim().length > 0

  return (
    <div className="dm-layout">
      <section className="dm-threads">
        <header className="dm-threads__header">
          <h1 className="dm-title">Messages</h1>
          <form className="dm-start" onSubmit={handleStartConversation}>
            <label className="dm-start__label" htmlFor="start-username">
              Start a new conversation
            </label>
            <div className="dm-start__controls">
              <input
                id="start-username"
                type="text"
                className="dm-start__input"
                placeholder="Enter a username"
                value={usernameInput}
                onChange={(event) => setUsernameInput(event.target.value)}
                disabled={starting}
              />
              <button
                type="submit"
                className="btn btn-sm btn-outline-light"
                disabled={starting}
              >
                {starting ? 'Starting…' : 'Start'}
              </button>
            </div>
            {startError && (
              <p className="dm-error" role="alert">
                {getErrorMessage(startError)}
              </p>
            )}
          </form>
        </header>
        {threadsLoading ? (
          <div className="dm-placeholder">Loading conversations…</div>
        ) : threadsError ? (
          <div className="dm-error" role="alert">
            {getErrorMessage(threadsError)}
          </div>
        ) : threads.length === 0 ? (
          <div className="dm-empty">No conversations yet. Start one above.</div>
        ) : (
          <ul className="dm-thread-list" role="list">
            {threads.map((thread) => {
              const isActive = thread.id === selectedThreadId
              const unread = thread.unreadCount || 0
              const preview = thread.lastMessage?.body ?? ''
              const previewText = preview.length > 120 ? `${preview.slice(0, 117)}…` : preview
              return (
                <li key={thread.id}>
                  <button
                    type="button"
                    className={`dm-thread-item${isActive ? ' dm-thread-item--active' : ''}`}
                    onClick={() => handleSelectThread(thread.id)}
                  >
                    <div className="dm-thread-item__primary">
                      <span className="dm-thread-item__name">
                        {thread.participant?.username ?? 'Unknown user'}
                      </span>
                      <span className="dm-thread-item__time">
                        {formatRelativeTime(
                          thread.lastMessage?.createdAt ??
                            thread.lastMessageAt ??
                            thread.createdAt
                        )}
                      </span>
                    </div>
                    {previewText && (
                      <p className="dm-thread-item__preview">{previewText}</p>
                    )}
                    {unread > 0 && (
                      <span className="dm-thread-item__badge">{unread}</span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>
      <section className="dm-pane">
        {selectedThreadId ? (
          <>
            <header className="dm-pane__header">
              <div>
                <h2 className="dm-pane__title">
                  {activeThread?.participant?.username ?? 'Conversation'}
                </h2>
                {activeThread && (
                  <p className="dm-pane__meta">
                    Started {formatRelativeTime(activeThread.createdAt)}
                  </p>
                )}
              </div>
            </header>
            {activeThreadError && (
              <div className="dm-error" role="alert">
                {getErrorMessage(activeThreadError)}
              </div>
            )}
            <div className="dm-messages" aria-live="polite">
              {activeHasMore && (
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary dm-load-more"
                  onClick={handleLoadOlder}
                  disabled={messagesLoading}
                >
                  {messagesLoading ? 'Loading…' : 'Load older messages'}
                </button>
              )}
              {messagesLoading && activeMessages.length === 0 ? (
                <div className="dm-placeholder">Loading messages…</div>
              ) : activeMessages.length === 0 ? (
                <div className="dm-empty">No messages yet. Say hello!</div>
              ) : (
                activeMessages.map((message) => {
                  const isMine = user && message.senderId === user.id
                  return (
                    <div
                      key={message.id}
                      className={`dm-message${isMine ? ' dm-message--mine' : ''}`}
                    >
                      <div className="dm-message__meta">
                        <span className="dm-message__author">
                          {isMine ? 'You' : message.senderUsername || 'Unknown'}
                        </span>
                        <span className="dm-message__time">
                          {formatRelativeTime(message.createdAt)}
                        </span>
                      </div>
                      <div className="dm-message__body">{message.body}</div>
                    </div>
                  )
                })
              )}
              <div ref={messagesEndRef} />
            </div>
            <form className="dm-composer" onSubmit={handleComposerSubmit}>
              <textarea
                className="dm-composer__input"
                placeholder="Write a message…"
                maxLength={MAX_MESSAGE_LENGTH}
                value={composerValue}
                onChange={(event) => setComposerValue(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                disabled={composerDisabled}
                rows={3}
              />
              <div className="dm-composer__footer">
                <span className="dm-composer__count">{remainingChars}</span>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!canSend}
                >
                  {sending ? 'Sending…' : 'Send'}
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="dm-empty dm-empty--pane">
            Select a conversation or start a new one to begin messaging.
          </div>
        )}
      </section>
    </div>
  )
}