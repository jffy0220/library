import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import {
  listSnippets,
  listTags,
  listPopularTags,
  getTrendingSnippets,
  getSavedSearch,
  getEngagementStatus,
  listBooks,
  listSavedSearches,
} from '../api'
import SearchBar from '../components/SearchBar'
import TagSelector from '../components/TagSelector'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { useAddSnippet } from '../components/AddSnippetProvider'
import StreakSummary from '../components/StreakSummary'
import CapturePrompt from '../components/CapturePrompt'
import { capture } from '../lib/analytics'

const PAGE_SIZE = 20
const INSIGHT_PROMPT_KEY = 'insightPromptDismissedOn'
const COLLECTION_STORAGE_KEY = 'library:readingList'

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function getHighlightTerms(query) {
  if (!query) return []
  return query
    .split(/\s+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 1)
}

function highlightText(text, terms) {
  if (!text || !Array.isArray(terms) || terms.length === 0) {
    return text
  }

  const safeTerms = terms.map(escapeRegex)
  const regex = new RegExp(`(${safeTerms.join('|')})`, 'gi')
  const parts = text.split(regex)

  return parts.map((part, index) => {
    if (!part) return null
    const isMatch = terms.some((term) => part.toLowerCase() === term.toLowerCase())
    return isMatch ? (
      <mark key={`highlight-${index}`} className="result-highlight">
        {part}
      </mark>
    ) : (
      <React.Fragment key={`fragment-${index}`}>{part}</React.Fragment>
    )
  })
}

const SHORTCUTS = [
  { id: 'add', description: 'Open quick add snippet', keys: [['Ctrl', 'K'], ['⌘', 'K']] },
  { id: 'shortcuts', description: 'Toggle keyboard shortcuts', keys: [['Shift', '?']] },
  { id: 'search', description: 'Focus search field', keys: [['/']] },
  { id: 'navigate', description: 'Move through search results', keys: [['Arrow ↑'], ['Arrow ↓']] },
  { id: 'select', description: 'Preview selected snippet', keys: [['Enter']] },
]

function KeyboardShortcutsDialog({ open, onClose }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose?.()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return undefined
    const previouslyFocused = document.activeElement
    const focusDialog = () => {
      if (!dialogRef.current) return
      const focusable = dialogRef.current.querySelector('[data-close-shortcuts]')
      if (focusable) {
        focusable.focus()
      }
    }
    const timer = window.setTimeout(focusDialog, 0)
    return () => {
      window.clearTimeout(timer)
      if (previouslyFocused && previouslyFocused.focus) {
        previouslyFocused.focus()
      }
    }
  }, [open])

  if (!open) return null

  return (
    <div className="shortcuts-overlay" role="presentation">
      <div
        className="shortcuts-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="keyboard-shortcuts-title"
        ref={dialogRef}
      >
        <div className="shortcuts-dialog__header">
          <h2 id="keyboard-shortcuts-title">Keyboard shortcuts</h2>
          <button
            type="button"
            className="btn-close btn-close-white"
            aria-label="Close shortcuts"
            onClick={onClose}
            data-close-shortcuts
          />
        </div>
        <ul className="shortcuts-list">
          {SHORTCUTS.map((shortcut) => (
            <li key={shortcut.id} className="shortcuts-list__item">
              <div className="shortcuts-list__keys" aria-hidden="true">
                {shortcut.keys.map((combo, index) => (
                  <span key={combo.join('+')} className="shortcuts-key-combo">
                    {combo.map((key) => (
                      <kbd key={key}>{key}</kbd>
                    ))}
                    {index < shortcut.keys.length - 1 ? <span className="shortcuts-key-separator">or</span> : null}
                  </span>
                ))}
              </div>
              <span className="shortcuts-list__description">{shortcut.description}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function SnippetDetailPanel({
  snippet,
  highlightTerms,
  onAddTagFilter,
  onToggleCollection,
  isCollected,
}) {
  const [copyState, setCopyState] = useState('idle')

  useEffect(() => {
    setCopyState('idle')
  }, [snippet?.id])

  useEffect(() => {
    if (copyState !== 'copied') return undefined
    const timeout = window.setTimeout(() => setCopyState('idle'), 2000)
    return () => window.clearTimeout(timeout)
  }, [copyState])

  if (!snippet) {
    return (
      <div className="detail-panel detail-panel--empty" role="region" aria-live="polite">
        <p>Select a snippet to see its details.</p>
      </div>
    )
  }

  const snippetText = snippet.text_snippet || ''
  const highlightedSnippet = useMemo(() => highlightText(snippetText, highlightTerms), [snippetText, highlightTerms])
  const highlightedTitle = useMemo(
    () => highlightText(snippet.book_name || 'Untitled', highlightTerms),
    [snippet.book_name, highlightTerms]
  )

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(snippetText)
      } else {
        const textarea = document.createElement('textarea')
        textarea.value = snippetText
        textarea.setAttribute('aria-hidden', 'true')
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      setCopyState('copied')
    } catch (err) {
      console.error('Failed to copy snippet', err)
      setCopyState('error')
    }
  }

  const created = snippet.created_utc ? new Date(snippet.created_utc) : null
  const collectionLabel = isCollected ? 'Remove from collection' : 'Add to collection'

  return (
    <div className="detail-panel" role="region" aria-live="polite">
      <header className="detail-panel__header">
        <div>
          <h2 className="detail-panel__title">{highlightedTitle}</h2>
          <div className="detail-panel__meta">
            {snippet.created_by_username ? <span>by {snippet.created_by_username}</span> : null}
            {created ? <span>{created.toLocaleString()}</span> : null}
            {snippet.page_number != null ? <span>p. {snippet.page_number}</span> : null}
            {snippet.chapter ? <span>ch. {snippet.chapter}</span> : null}
            {snippet.verse ? <span>v. {snippet.verse}</span> : null}
            {(snippet.visibility || '').toLowerCase() === 'private' ? (
              <span className="badge text-bg-warning">Private</span>
            ) : null}
          </div>
        </div>
        <div className="detail-panel__actions" role="group" aria-label="Snippet actions">
          <button
            type="button"
            className="btn btn-outline-light btn-sm"
            onClick={handleCopy}
          >
            Copy
          </button>
          <Link className="btn btn-outline-light btn-sm" to={`/snippet/${snippet.id}`}>
            Open
          </Link>
          <Link className="btn btn-outline-light btn-sm" to={`/snippet/${snippet.id}#comments`}>
            Comments
          </Link>
          <button
            type="button"
            className={`btn btn-sm ${isCollected ? 'btn-success' : 'btn-outline-light'}`}
            onClick={() => onToggleCollection(snippet.id)}
          >
            {collectionLabel}
          </button>
        </div>
      </header>
      <div className="detail-panel__body">
        <blockquote className="detail-panel__snippet" tabIndex={0}>
          {highlightedSnippet}
        </blockquote>
        {snippet.thoughts ? (
          <div className="detail-panel__thoughts">
            <h3>Reflection</h3>
            <p>{snippet.thoughts}</p>
          </div>
        ) : null}
        {snippet.tags && snippet.tags.length ? (
          <div className="detail-panel__tags" role="group" aria-label="Snippet tags">
            {snippet.tags.map((tag) => (
              <button
                key={tag.id || tag.name}
                type="button"
                className="tag-chip tag-chip--outlined"
                onClick={() => onAddTagFilter(tag.name)}
              >
                #{tag.name}
              </button>
            ))}
          </div>
        ) : null}
        <div className="detail-panel__status" role="status">
          {copyState === 'copied' ? 'Snippet copied to clipboard.' : null}
          {copyState === 'error' ? 'Unable to copy snippet.' : null}
          {isCollected ? 'Saved to your local collection.' : null}
        </div>
      </div>
    </div>
  )
}

export default function List() {
  const { user } = useAuth()
  const { open: openAddSnippet } = useAddSnippet()
  const [searchParams, setSearchParams] = useSearchParams()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [meta, setMeta] = useState({ total: 0, nextPage: null })
  const [availableTags, setAvailableTags] = useState([])
  const [popularTags, setPopularTags] = useState([])
  const [trending, setTrending] = useState([])
  const [sidebarLoading, setSidebarLoading] = useState(true)
  const [sidebarError, setSidebarError] = useState(null)
  const [engagement, setEngagement] = useState(null)
  const [engagementLoading, setEngagementLoading] = useState(false)
  const [engagementError, setEngagementError] = useState(null)
  const [savedSearchNotice, setSavedSearchNotice] = useState(null)
  const [promptDismissed, setPromptDismissed] = useState(false)
  const [bookOptions, setBookOptions] = useState([])
  const [savedSearches, setSavedSearches] = useState([])
  const [savedSearchesLoading, setSavedSearchesLoading] = useState(false)
  const [savedSearchesError, setSavedSearchesError] = useState(null)
  const [collection, setCollection] = useState(() => {
    if (typeof window === 'undefined') {
      return []
    }
    try {
      const stored = window.localStorage?.getItem(COLLECTION_STORAGE_KEY)
      const parsed = stored ? JSON.parse(stored) : []
      if (Array.isArray(parsed)) return parsed
    } catch (err) {
      console.warn('Unable to read saved collection', err)
    }
    return []
  })
  const [selectedSnippetId, setSelectedSnippetId] = useState(null)
  const [showShortcuts, setShowShortcuts] = useState(false)

  const resultsListRef = useRef(null)
  const sentinelRef = useRef(null)
  const searchInputRef = useRef(null)
  const lastQueryKeyRef = useRef(null)

  const q = searchParams.get('q') || ''
  const sort = searchParams.get('sort') || 'recent'
  const book = searchParams.get('book') || ''
  const pageParam = Number.parseInt(searchParams.get('page') || '1', 10)
  const page = Number.isNaN(pageParam) || pageParam < 1 ? 1 : pageParam
  const selectedTags = useMemo(() => {
    const multi = searchParams.getAll('tag')
    if (multi.length > 0) return multi
    const combined = searchParams.get('tags')
    if (combined) {
      return combined
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    }
    return []
  }, [searchParams])
  const tagsKey = selectedTags.join('|')
  const highlightTerms = useMemo(() => getHighlightTerms(q), [q])

  useEffect(() => {
    try {
      window.localStorage?.setItem(COLLECTION_STORAGE_KEY, JSON.stringify(collection))
    } catch (err) {
      console.warn('Unable to persist collection', err)
    }
  }, [collection])

  useEffect(() => {
    const handler = (event) => {
      if (event.defaultPrevented) return
      const target = event.target
      const tagName = target?.tagName?.toLowerCase()
      const isFormField = ['input', 'textarea', 'select'].includes(tagName)
      if ((event.key === '?' || (event.shiftKey && event.key === '/')) && !event.metaKey && !event.ctrlKey && !event.altKey) {
        if (isFormField) return
        event.preventDefault()
        setShowShortcuts((prev) => !prev)
      }
      if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) {
        if (isFormField) return
        event.preventDefault()
        searchInputRef.current?.focus()
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        openAddSnippet()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [openAddSnippet])

  useEffect(() => {
    if (!user) {
      setEngagement(null)
      setPromptDismissed(false)
      return
    }
    const tz = (() => {
      try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone
      } catch (err) {
        return undefined
      }
    })()
    let ignore = false
    setEngagementLoading(true)
    setEngagementError(null)
    ;(async () => {
      try {
        const data = await getEngagementStatus({ timezone: tz })
        if (!ignore) {
          setEngagement(data)
        }
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load engagement status', err)
          setEngagementError('We could not load your streak information.')
        }
      } finally {
        if (!ignore) {
          setEngagementLoading(false)
        }
      }
    })()
    return () => {
      ignore = true
    }
  }, [user])

  useEffect(() => {
    if (!user) return
    try {
      const today = new Date().toISOString().slice(0, 10)
      const stored = window.localStorage?.getItem(INSIGHT_PROMPT_KEY)
      setPromptDismissed(stored === today)
    } catch (err) {
      setPromptDismissed(false)
    }
  }, [user])

  const handleDismissPrompt = useCallback(() => {
    setPromptDismissed(true)
    try {
      const today = new Date().toISOString().slice(0, 10)
      window.localStorage?.setItem(INSIGHT_PROMPT_KEY, today)
    } catch (err) {
      // ignore storage errors
    }
  }, [])

  const applySavedSearch = useCallback(
    (saved) => {
      if (!saved) return
      const query = saved.query || {}
      const tags = []
      if (Array.isArray(query.tags)) {
        tags.push(...query.tags)
      }
      if (Array.isArray(query.tag)) {
        tags.push(...query.tag)
      }
      const normalizedTags = tags
        .map((tag) => (tag || '').trim())
        .filter(Boolean)

      setSearchParams(() => {
        const next = new URLSearchParams()
        const nextQ = (query.q || '').trim()
        if (nextQ) next.set('q', nextQ)
        const nextBook = (query.book || '').trim()
        if (nextBook) next.set('book', nextBook)
        normalizedTags.forEach((tag) => next.append('tag', tag))
        const sortValue = (query.sort || '').trim()
        if (sortValue) next.set('sort', sortValue)
        next.set('page', '1')
        return next
      })
      setSavedSearchNotice({ id: saved.id, name: saved.name })
    },
    [setSearchParams]
  )

  useEffect(() => {
    const savedSearchId = searchParams.get('savedSearch')
    if (!user || !savedSearchId) return
    let ignore = false
    ;(async () => {
      try {
        const saved = await getSavedSearch(savedSearchId)
        if (!ignore) {
          applySavedSearch(saved)
        }
      } catch (err) {
        if (!ignore) {
          console.error('Unable to load saved search', err)
          setSavedSearchNotice({ id: savedSearchId, name: 'Saved search', error: true })
        }
      } finally {
        if (!ignore) {
          setSearchParams((prev) => {
            const next = new URLSearchParams(prev)
            next.delete('savedSearch')
            return next
          })
        }
      }
    })()
    return () => {
      ignore = true
    }
  }, [searchParams, user, applySavedSearch, setSearchParams])

  useEffect(() => {
    let ignore = false
    setSidebarLoading(true)
    setSidebarError(null)
    ;(async () => {
      try {
        const [allTags, popular, trendingSnippets, books] = await Promise.all([
          listTags({ limit: 200 }),
          listPopularTags({ days: 7, limit: 12 }),
          getTrendingSnippets({ limit: 6 }),
          listBooks({ limit: 50 }),
        ])
        if (!ignore) {
          setAvailableTags(allTags)
          setPopularTags(popular)
          setTrending(trendingSnippets)
          setBookOptions(Array.isArray(books) ? books : [])
        }
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load discovery data', err)
          setSidebarError('Some discovery data failed to load.')
        }
      } finally {
        if (!ignore) setSidebarLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!user) {
      setSavedSearches([])
      return
    }
    let ignore = false
    setSavedSearchesLoading(true)
    setSavedSearchesError(null)
    ;(async () => {
      try {
        const data = await listSavedSearches()
        if (!ignore) {
          setSavedSearches(Array.isArray(data) ? data : [])
        }
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load saved searches', err)
          if (err?.response?.status !== 401) {
            setSavedSearchesError('Saved searches are unavailable right now.')
          }
        }
      } finally {
        if (!ignore) setSavedSearchesLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [user])

  const updateSearchParams = useCallback(
    (updates) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        let shouldResetPage = false
        if ('q' in updates) {
          const nextQ = updates.q?.trim()
          if (nextQ) next.set('q', nextQ)
          else next.delete('q')
          shouldResetPage = true
        }
        if ('sort' in updates) {
          const nextSort = updates.sort
          if (nextSort && nextSort !== 'recent') next.set('sort', nextSort)
          else next.delete('sort')
          shouldResetPage = true
        }
        if ('book' in updates) {
          const nextBook = updates.book?.trim()
          if (nextBook) next.set('book', nextBook)
          else next.delete('book')
          shouldResetPage = true
        }
        if ('tags' in updates) {
          next.delete('tag')
          next.delete('tags')
          const tagList = (updates.tags || [])
            .map((tag) => tag.trim())
            .filter(Boolean)
          tagList.forEach((tag) => next.append('tag', tag))
          shouldResetPage = true
        }
        if ('page' in updates) {
          const nextPage = Number.parseInt(updates.page, 10)
          if (Number.isFinite(nextPage) && nextPage > 1) {
            next.set('page', String(nextPage))
          } else {
            next.delete('page')
          }
        } else if (shouldResetPage) {
          next.delete('page')
        }
        return next
      })
    },
    [setSearchParams]
  )

  const handleAddTagFilter = useCallback(
    (tagName) => {
      const normalized = (tagName || '').trim()
      if (!normalized) return
      if (selectedTags.some((tag) => tag.toLowerCase() === normalized.toLowerCase())) return
      updateSearchParams({ tags: [...selectedTags, normalized], page: 1 })
    },
    [selectedTags, updateSearchParams]
  )

  const goToPage = useCallback(
    (nextPageValue) => {
      const target = Math.max(1, Number.parseInt(nextPageValue, 10) || 1)
      if (target === page) return
      updateSearchParams({ page: target })
    },
    [page, updateSearchParams]
  )

  useEffect(() => {
    let ignore = false
    const queryKey = JSON.stringify({ q, book, sort, tagsKey })
    const isNewQuery = lastQueryKeyRef.current !== queryKey
    const isFirstPage = page <= 1 || isNewQuery

    if (isNewQuery) {
      setRows([])
      setMeta({ total: 0, nextPage: null })
    }

    setError(null)
    if (isFirstPage) {
      setLoading(true)
      setLoadingMore(false)
    } else {
      setLoadingMore(true)
    }

    ;(async () => {
      const started = typeof performance !== 'undefined' ? performance.now() : 0
      try {
        const data = await listSnippets({
          q: q || undefined,
          book: book || undefined,
          tags: selectedTags,
          sort,
          limit: PAGE_SIZE,
          page,
        })
        if (ignore) return
        const items = Array.isArray(data?.items) ? data.items : []
        if (isFirstPage) {
          setRows(items)
        } else {
          setRows((prev) => {
            const existingIds = new Set(prev.map((item) => item.id))
            const deduped = items.filter((item) => !existingIds.has(item.id))
            return [...prev, ...deduped]
          })
        }
        setMeta({
          total: typeof data?.total === 'number' ? data.total : items.length,
          nextPage: typeof data?.nextPage === 'number' ? data.nextPage : null,
        })
        const durationMs = typeof performance !== 'undefined' ? Math.round(performance.now() - started) : undefined
        const trimmedQuery = (q || '').trim()
        const hasSearchCriteria = Boolean(trimmedQuery || book || selectedTags.length > 0)
        if (isFirstPage && hasSearchCriteria) {
          const filtersPayload = {
            tags: [...selectedTags],
            book: book || null,
            date_range: {
              from: null,
              to: null,
            },
          }
          capture({
            event: 'search_performed',
            duration_ms: durationMs,
            props: {
              q_len: trimmedQuery.length,
              filters: filtersPayload,
              results_count: items.length,
            },
          })
          if (items.length === 0) {
            capture({
              event: 'search_zero_results',
              props: {
                q: trimmedQuery,
                filters: filtersPayload,
              },
            })
          }
        }
        lastQueryKeyRef.current = queryKey
      } catch (err) {
        if (ignore || err?.response?.status === 401) return
        console.error('Failed to load snippets', err)
        const detail = err?.response?.data?.detail
        setError(detail || 'Failed to load snippets.')
        if (isFirstPage) {
          setRows([])
          setMeta({ total: 0, nextPage: null })
        }
      } finally {
        if (!ignore) {
          setLoading(false)
          setLoadingMore(false)
        }
      }
    })()

    return () => {
      ignore = true
    }
  }, [q, book, sort, tagsKey, page, selectedTags])

  useEffect(() => {
    if (rows.length === 0) {
      setSelectedSnippetId(null)
      return
    }
    setSelectedSnippetId((prev) => {
      if (prev && rows.some((item) => item.id === prev)) return prev
      return rows[0].id
    })
  }, [rows])

  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return undefined
    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries
        if (!entry?.isIntersecting) return
        if (!meta.nextPage || loading || loadingMore || error) return
        goToPage(meta.nextPage)
      },
      { rootMargin: '120px' }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [meta.nextPage, loading, loadingMore, error, goToPage])

  const toggleCollection = useCallback((snippetId) => {
    setCollection((prev) => {
      const exists = prev.includes(snippetId)
      if (exists) {
        return prev.filter((id) => id !== snippetId)
      }
      return [...prev, snippetId]
    })
  }, [])

  const selectedSnippet = useMemo(
    () => rows.find((item) => item.id === selectedSnippetId) || null,
    [rows, selectedSnippetId]
  )

  const totalCount = meta.total || 0
  const hasNextPage = meta.nextPage != null
  const hasVisibleResults = !error && rows.length > 0
  const showingRangeStart = hasVisibleResults ? 1 : 0
  const showingRangeEnd = hasVisibleResults ? Math.min(rows.length, totalCount || rows.length) : 0
  const summaryText = loading && rows.length === 0 ? 'Loading snippets…' : `${totalCount} snippet${totalCount === 1 ? '' : 's'} found`
  const trendingCommentTotal = trending.reduce((total, item) => total + (item.recent_comment_count || 0), 0)
  const shouldShowPrompt = Boolean(user && engagement && engagement.showCapturePrompt && !promptDismissed)

  const focusResultAt = useCallback((index) => {
    const listNode = resultsListRef.current
    if (!listNode) return
    const items = listNode.querySelectorAll('[data-result-index]')
    if (!items || !items.length) return
    const target = items[index]
    if (target && target.focus) {
      target.focus()
    }
  }, [])

  const handleResultKeyDown = useCallback(
    (event, index) => {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        focusResultAt(Math.min(rows.length - 1, index + 1))
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        focusResultAt(Math.max(0, index - 1))
      }
    },
    [rows.length, focusResultAt]
  )

  const collectionIncludesSelected = selectedSnippet ? collection.includes(selectedSnippet.id) : false

  const handleClearSavedSearch = useCallback(() => {
    setSavedSearchNotice(null)
    setSearchParams(() => new URLSearchParams())
  }, [setSearchParams])

  return (
    <div className="home-page">
      {user ? (
        <div className="mb-4 d-flex flex-column gap-3">
          {engagementError && !engagementLoading ? (
            <div className="alert alert-warning" role="status">
              {engagementError}
            </div>
          ) : null}
          {engagement?.streak ? <StreakSummary streak={engagement.streak} /> : null}
          {shouldShowPrompt ? <CapturePrompt onDismiss={handleDismissPrompt} /> : null}
          {savedSearchNotice ? (
            <div className="alert alert-primary d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-2">
              <div>
                {savedSearchNotice.error ? 'We could not load that saved search.' : (
                  <>Showing saved search <strong>{savedSearchNotice.name}</strong>.</>
                )}
              </div>
              <button type="button" className="btn btn-outline-primary btn-sm" onClick={handleClearSavedSearch}>
                Clear
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="callout">
          Want to share your own discoveries?{' '}
          <Link to="/login" className="alert-link">
            Sign in
          </Link>{' '}
          to contribute snippets and join the discussion.
        </div>
      )}

      {!user && (
        <section className="home-hero">
          <div className="home-hero__content">
            <h1 className="home-hero__headline">Collect the lines worth remembering</h1>
            <p className="home-hero__lead">
              Build a feed inspired by your favorite communities on Facebook, X, and Reddit. Follow what the library is reading, remix tags, and bring new color to the conversation.
            </p>
            <div className="home-hero__actions">
              <Link className="btn btn-primary" to="/register">
                Join the library
              </Link>
              <Link className="btn btn-outline-light" to="/groups">
                Preview the feed
              </Link>
            </div>
          </div>
          <div className="home-hero__stats">
            <div className="stat-tile">
              <span className="stat-value">{totalCount.toLocaleString()}</span>
              <span className="stat-label">Snippets indexed</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{popularTags.length}</span>
              <span className="stat-label">Trending tags this week</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{trendingCommentTotal.toLocaleString()}</span>
              <span className="stat-label">Fresh comments</span>
            </div>
          </div>
        </section>
      )}

      <div className="library-shell">
        <aside className="library-shell__filters" aria-label="Filters">
          <section className="filters-card">
            <header className="filters-card__header">
              <h2>Library filters</h2>
              <div className="filters-card__actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={openAddSnippet}
                  aria-keyshortcuts="Ctrl+K Meta+K"
                >
                  Quick add
                </button>
                <button
                  type="button"
                  className="btn btn-outline-light btn-sm"
                  onClick={() => setShowShortcuts(true)}
                  aria-keyshortcuts="Shift+/"
                >
                  Shortcuts
                </button>
              </div>
            </header>
            <div className="filters-card__section">
              <SearchBar
                value={q}
                onSearch={(next) => updateSearchParams({ q: next, page: 1 })}
                placeholder="Search snippets…"
                inputRef={searchInputRef}
              />
              <p className="search-help">Press / to jump to search.</p>
            </div>
            <div className="filters-card__section">
              <label className="filters-card__label" htmlFor="snippet-sort">
                Sort by
              </label>
              <select
                id="snippet-sort"
                className="form-select form-select-sm"
                value={sort}
                onChange={(event) => updateSearchParams({ sort: event.target.value, page: 1 })}
              >
                <option value="recent">Most recent</option>
                <option value="trending">Trending</option>
              </select>
            </div>
            <div className="filters-card__section">
              <label className="filters-card__label" htmlFor="book-filter">
                Book
              </label>
              <input
                id="book-filter"
                className="form-control form-control-sm filters-card__input"
                type="text"
                list="book-filter-options"
                value={book}
                onChange={(event) => updateSearchParams({ book: event.target.value, page: 1 })}
                placeholder="Filter by book title"
              />
              <datalist id="book-filter-options">
                {bookOptions.map((item) => (
                  <option key={item.id || item.name} value={item.name || item.title || ''} />
                ))}
              </datalist>
            </div>
            <div className="filters-card__section">
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h3 className="filters-card__label mb-0">Tags</h3>
                {selectedTags.length > 0 ? (
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0"
                    onClick={() => updateSearchParams({ tags: [], page: 1 })}
                  >
                    Clear tags
                  </button>
                ) : null}
              </div>
              <TagSelector
                availableTags={availableTags}
                value={selectedTags}
                onChange={(next) => updateSearchParams({ tags: next, page: 1 })}
                showCounts
              />
            </div>
            <div className="filters-card__section">
              <h3 className="filters-card__label">Saved searches</h3>
              {user ? (
                savedSearchesLoading ? (
                  <p className="text-muted small">Loading…</p>
                ) : savedSearchesError ? (
                  <p className="text-muted small">{savedSearchesError}</p>
                ) : savedSearches.length === 0 ? (
                  <p className="text-muted small">No saved searches yet.</p>
                ) : (
                  <ul className="filters-list" role="list">
                    {savedSearches.map((saved) => (
                      <li key={saved.id}>
                        <button
                          type="button"
                          className="filters-list__button"
                          onClick={() => applySavedSearch(saved)}
                        >
                          {saved.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              ) : (
                <p className="text-muted small">Sign in to save your favorite searches.</p>
              )}
            </div>
            <div className="filters-card__section">
              <h3 className="filters-card__label">Popular tags</h3>
              {sidebarLoading ? (
                <p className="text-muted small">Loading…</p>
              ) : sidebarError ? (
                <p className="text-muted small">{sidebarError}</p>
              ) : popularTags.length === 0 ? (
                <p className="text-muted small">No trending tags yet.</p>
              ) : (
                <div className="popular-tag-list">
                  {popularTags.map((tag) => (
                    <button
                      key={tag.id}
                      type="button"
                      className="tag-chip tag-chip--outlined"
                      onClick={() => handleAddTagFilter(tag.name)}
                    >
                      #{tag.name}
                      {typeof tag.usage_count === 'number' ? (
                        <span className="tag-chip__count">{tag.usage_count}</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="filters-card__section">
              <h3 className="filters-card__label">Popular this week</h3>
              {sidebarLoading ? (
                <p className="text-muted small">Loading…</p>
              ) : trending.length === 0 ? (
                <p className="text-muted small">No trending snippets yet.</p>
              ) : (
                <ul className="filters-list" role="list">
                  {trending.map((item) => {
                    const tagNames = Array.isArray(item.tags)
                      ? item.tags.map((tag) => tag.name).filter(Boolean)
                      : []
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          className="filters-list__button"
                          onClick={() => {
                            if (tagNames.length > 0) {
                              updateSearchParams({ tags: tagNames, page: 1 })
                            } else if (item.book_name) {
                              updateSearchParams({ q: item.book_name, page: 1 })
                            }
                            setSelectedSnippetId(item.id)
                          }}
                        >
                          <span className="fw-semibold">{item.book_name || 'Untitled'}</span>
                          <span className="filters-list__meta">
                            {item.recent_comment_count} comment{item.recent_comment_count === 1 ? '' : 's'}
                          </span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </section>
        </aside>

        <section className="library-shell__results" aria-label="Search results">
          <header className="results-header">
            <div>
              <p className="results-summary" role="status">
                {summaryText}
              </p>
              <div className="results-meta">
                {hasVisibleResults ? (
                  <span>
                    Showing {showingRangeStart}-{showingRangeEnd}
                  </span>
                ) : null}
                {q ? <span>Keyword: “{q}”</span> : null}
                {book ? <span>Book: “{book}”</span> : null}
                {selectedTags.length > 0 ? <span>Tags: {selectedTags.join(', ')}</span> : null}
              </div>
            </div>
          </header>

          {error ? <div className="alert alert-danger">{error}</div> : null}
          {!error && loading && rows.length === 0 ? (
            <div className="snippet-card text-muted">Loading feed…</div>
          ) : null}
          {!loading && !error && rows.length === 0 ? (
            <div className="snippet-card text-muted">No snippets found. Try adjusting your filters.</div>
          ) : null}

          <ul
            className="results-list"
            role="listbox"
            aria-label="Snippet search results"
            ref={resultsListRef}
          >
            {rows.map((r, index) => {
              const preview = (r.text_snippet || '').slice(0, 320)
              const showEllipsis = r.text_snippet && r.text_snippet.length > 320
              const visibility = (r.visibility || '').toLowerCase()
              const isPrivate = visibility === 'private'
              const isActive = selectedSnippetId === r.id
              return (
                <li key={r.id} className="results-list__item">
                  <button
                    type="button"
                    className={`result-card ${isActive ? 'result-card--active' : ''}`}
                    onClick={() => setSelectedSnippetId(r.id)}
                    onFocus={() => setSelectedSnippetId(r.id)}
                    data-result-index={index}
                    role="option"
                    aria-selected={isActive}
                    onKeyDown={(event) => handleResultKeyDown(event, index)}
                  >
                    <div className="result-card__header">
                      <h3 className="result-card__title">{highlightText(r.book_name || 'Untitled', highlightTerms)}</h3>
                      <span className="result-card__timestamp">
                        {new Date(r.created_utc).toLocaleString()}
                      </span>
                    </div>
                    <div className="result-card__meta">
                      {r.created_by_username ? <span>by {r.created_by_username}</span> : null}
                      {r.page_number != null ? <span>p. {r.page_number}</span> : null}
                      {r.chapter ? <span>ch. {r.chapter}</span> : null}
                      {r.verse ? <span>v. {r.verse}</span> : null}
                      {isPrivate ? <span className="badge text-bg-warning ms-2">Private</span> : null}
                    </div>
                    <p className="result-card__preview">
                      {highlightText(preview, highlightTerms)}
                      {showEllipsis ? '…' : ''}
                    </p>
                    {r.tags && r.tags.length > 0 ? (
                      <div className="result-card__tags">
                        {r.tags.slice(0, 6).map((tag) => (
                          <span key={tag.id} className="result-card__tag">#{tag.name}</span>
                        ))}
                      </div>
                    ) : null}
                  </button>
                </li>
              )
            })}
          </ul>

          {loadingMore ? (
            <div className="snippet-card text-muted d-flex align-items-center gap-2" role="status">
              <span className="spinner-border spinner-border-sm" aria-hidden="true"></span>
              <span>Loading more results…</span>
            </div>
          ) : null}

          {hasNextPage ? (
            <button
              type="button"
              className="btn btn-outline-secondary w-100 mt-3"
              onClick={() => goToPage(meta.nextPage)}
              disabled={loadingMore}
            >
              Load more
            </button>
          ) : null}

          <div ref={sentinelRef} aria-hidden="true" />
        </section>

        <aside className="library-shell__details" aria-label="Snippet details">
          <SnippetDetailPanel
            snippet={selectedSnippet}
            highlightTerms={highlightTerms}
            onAddTagFilter={handleAddTagFilter}
            onToggleCollection={toggleCollection}
            isCollected={collectionIncludesSelected}
          />
          {collection.length > 0 ? (
            <div className="collection-summary" role="status">
              {collection.length} snippet{collection.length === 1 ? '' : 's'} saved for later.
            </div>
          ) : null}
        </aside>
      </div>

      <KeyboardShortcutsDialog open={showShortcuts} onClose={() => setShowShortcuts(false)} />
    </div>
  )
}
