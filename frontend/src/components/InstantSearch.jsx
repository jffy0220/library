import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import {
  createSavedSearch,
  deleteSavedSearch,
  listSavedSearches,
  searchSnippets,
  updateSavedSearch
} from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'

const QUICK_RANGES = [
  { key: 'any', label: 'Any time' },
  { key: '7d', label: 'Last 7 days', days: 7 },
  { key: '30d', label: 'Last 30 days', days: 30 },
  { key: '365d', label: 'Last year', days: 365 }
]

const RECENT_STORAGE_KEY = 'instantSearchRecent'
const MAX_RECENT_SEARCHES = 6

const isFormInput = (target) => {
  if (!target) return false
  const tag = target.tagName
  if (!tag) return false
  const name = tag.toLowerCase()
  return name === 'input' || name === 'textarea' || name === 'select' || target.isContentEditable
}

const normalizeTag = (value) => {
  if (typeof value !== 'string') return ''
  return value.replace(/^#/, '').trim()
}

const normalizeTags = (tags) => {
  if (!Array.isArray(tags)) return []
  return tags
    .map((tag) => normalizeTag(tag))
    .filter(Boolean)
}

const areQueriesEqual = (a, b) => {
  if (!a || !b) return false
  const tagA = normalizeTags(a.tags)
  const tagB = normalizeTags(b.tags)
  if (tagA.length !== tagB.length) return false
  const sortedA = [...tagA].sort()
  const sortedB = [...tagB].sort()
  for (let i = 0; i < sortedA.length; i += 1) {
    if (sortedA[i] !== sortedB[i]) return false
  }
  return (
    (a.q || '').trim() === (b.q || '').trim() &&
    (a.book || '').trim() === (b.book || '').trim() &&
    (a.createdFrom || '') === (b.createdFrom || '') &&
    (a.createdTo || '') === (b.createdTo || '')
  )
}

const loadRecentSearches = () => {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(RECENT_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((entry) => entry && typeof entry === 'object' && entry.query)
  } catch (error) {
    return []
  }
}

const persistRecentSearches = (entries) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_RECENT_SEARCHES)))
  } catch (error) {
    /* noop */
  }
}

function rangeKeyFromQuery(query) {
  if (!query) return 'any'
  if (query.range && QUICK_RANGES.some((option) => option.key === query.range)) {
    return query.range
  }
  if (query.createdFrom) {
    const from = new Date(query.createdFrom)
    if (!Number.isNaN(from.getTime())) {
      const diffMs = Date.now() - from.getTime()
      const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))
      const match = QUICK_RANGES.find((option) => option.days && Math.abs(option.days - diffDays) <= 2)
      if (match) {
        return match.key
      }
    }
  }
  return 'any'
}

function computeCreatedFrom(rangeKey) {
  const option = QUICK_RANGES.find((item) => item.key === rangeKey)
  if (!option || !option.days) {
    return null
  }
  const ms = option.days * 24 * 60 * 60 * 1000
  const from = new Date(Date.now() - ms)
  return from.toISOString()
}

export default function InstantSearch({ open, onOpen, onClose }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const savedSearchRequest = useRef(null)

  const [query, setQuery] = useState('')
  const [tags, setTags] = useState([])
  const [tagDraft, setTagDraft] = useState('')
  const [book, setBook] = useState('')
  const [rangeKey, setRangeKey] = useState('any')
  const [page, setPage] = useState(1)
  const [results, setResults] = useState([])
  const [total, setTotal] = useState(0)
  const [nextPage, setNextPage] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [savedSearches, setSavedSearches] = useState([])
  const [recentSearches, setRecentSearches] = useState(() => loadRecentSearches())

  const debouncedQuery = useDebouncedValue(query, 120)
  const createdFrom = useMemo(() => computeCreatedFrom(rangeKey), [rangeKey])
  const trimmedBook = book.trim()
  const hasCriteria = useMemo(() => {
    return Boolean(debouncedQuery.trim() || trimmedBook || createdFrom || tags.length)
  }, [debouncedQuery, trimmedBook, createdFrom, tags.length])

  const fetchSavedSearches = useCallback(async () => {
    if (!user) {
      setSavedSearches([])
      return
    }
    try {
      const request = listSavedSearches()
      savedSearchRequest.current = request
      const data = await request
      if (savedSearchRequest.current !== request) return
      setSavedSearches(Array.isArray(data) ? data : [])
    } catch (requestError) {
      // ignore fetch errors, surfaced in UI via actions
    }
  }, [user])

  useEffect(() => {
    if (!open) return
    if (inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const handler = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        if (onClose) onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  useEffect(() => {
    const handler = (event) => {
      if (event.defaultPrevented) return
      if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) {
        if (isFormInput(event.target)) return
        event.preventDefault()
        if (onOpen) onOpen()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onOpen])

  useEffect(() => {
    if (!open || !hasCriteria) {
      setLoading(false)
      setError(null)
      if (!hasCriteria) {
        setResults([])
        setTotal(0)
        setNextPage(null)
        setActiveIndex(-1)
      }
      return undefined
    }

    let cancelled = false
    const params = {
      limit: 10,
      page
    }
    const trimmedQuery = debouncedQuery.trim()
    if (trimmedQuery) {
      params.q = trimmedQuery
    }
    if (tags.length > 0) {
      params.tags = tags
    }
    if (trimmedBook) {
      params.book = trimmedBook
    }
    if (createdFrom) {
      params.createdFrom = createdFrom
    }

    setLoading(true)
    setError(null)

    searchSnippets(params)
      .then((data) => {
        if (cancelled) return
        const items = Array.isArray(data?.items) ? data.items : []
        setResults((prev) => (page > 1 ? [...prev, ...items] : items))
        setTotal(typeof data?.total === 'number' ? data.total : items.length)
        setNextPage(data?.nextPage ?? null)
        setActiveIndex((prev) => {
          if (page > 1) {
            if (prev >= 0) return prev
            return items.length > 0 ? 0 : -1
          }
          return items.length > 0 ? 0 : -1
        })
      })
      .catch((requestError) => {
        if (cancelled) return
        const message =
          requestError?.response?.data?.detail || requestError?.message || 'Search is unavailable right now.'
        setError(message)
        setResults([])
        setTotal(0)
        setNextPage(null)
        setActiveIndex(-1)
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [open, debouncedQuery, tags, trimmedBook, createdFrom, page, hasCriteria])

  useEffect(() => {
    if (open && user) {
      fetchSavedSearches()
    }
  }, [open, user, fetchSavedSearches])

  useEffect(() => {
    if (!user) {
      setSavedSearches([])
    }
  }, [user])

  const applyQueryState = useCallback((state) => {
    setQuery((state?.q || '').toString())
    setTags(normalizeTags(state?.tags))
    setBook((state?.book || '').toString())
    setRangeKey(rangeKeyFromQuery(state))
    setPage(1)
    setActiveIndex(-1)
  }, [])

  const recordRecentSearch = useCallback(
    (queryState) => {
      if (!queryState) return
      const entry = {
        query: {
          ...queryState,
          tags: normalizeTags(queryState.tags)
        },
        savedAt: new Date().toISOString()
      }
      setRecentSearches((prev) => {
        const filtered = prev.filter((item) => !areQueriesEqual(item.query, entry.query))
        const next = [entry, ...filtered].slice(0, MAX_RECENT_SEARCHES)
        persistRecentSearches(next)
        return next
      })
    },
    []
  )

  const buildQueryPayload = useCallback(() => {
    const trimmedQuery = query.trim()
    return {
      q: trimmedQuery,
      tags: normalizeTags(tags),
      book: trimmedBook,
      createdFrom,
      createdTo: null,
      range: rangeKey
    }
  }, [query, tags, trimmedBook, createdFrom, rangeKey])

  const handleSelectResult = useCallback(
    (result) => {
      if (!result) return
      const payload = buildQueryPayload()
      recordRecentSearch(payload)
      if (onClose) {
        onClose()
      }
      navigate(`/snippet/${result.id}`)
    },
    [buildQueryPayload, navigate, onClose, recordRecentSearch]
  )

  const handleSaveSearch = useCallback(async () => {
    if (!user) {
      return
    }
    const payload = buildQueryPayload()
    const hasAny = Boolean(payload.q || payload.tags.length || payload.book || payload.createdFrom)
    if (!hasAny) {
      setError('Add a query or filter before saving a search.')
      return
    }
    const defaultName = payload.q || 'Saved search'
    const name = window.prompt('Name this search', defaultName)
    if (!name || !name.trim()) return
    try {
      const created = await createSavedSearch({ name: name.trim(), query: payload })
      setSavedSearches((prev) => [created, ...prev.filter((item) => item.id !== created.id)])
    } catch (requestError) {
      const message =
        requestError?.response?.data?.detail || requestError?.message || 'Unable to save this search.'
      setError(message)
    }
  }, [buildQueryPayload, user])

  const handleRenameSearch = useCallback(async (savedSearch) => {
    if (!savedSearch) return
    const name = window.prompt('Rename saved search', savedSearch.name)
    if (!name || !name.trim()) return
    try {
      const updated = await updateSavedSearch(savedSearch.id, { name: name.trim() })
      setSavedSearches((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
    } catch (requestError) {
      const message =
        requestError?.response?.data?.detail || requestError?.message || 'Unable to rename this saved search.'
      setError(message)
    }
  }, [])

  const handleDeleteSearch = useCallback(async (savedSearch) => {
    if (!savedSearch) return
    const confirmed = window.confirm(`Delete saved search “${savedSearch.name}”?`)
    if (!confirmed) return
    try {
      await deleteSavedSearch(savedSearch.id)
      setSavedSearches((prev) => prev.filter((item) => item.id !== savedSearch.id))
    } catch (requestError) {
      const message =
        requestError?.response?.data?.detail || requestError?.message || 'Unable to delete this saved search.'
      setError(message)
    }
  }, [])

  const handleApplySaved = useCallback(
    (savedSearch) => {
      if (!savedSearch) return
      applyQueryState(savedSearch.query || {})
    },
    [applyQueryState]
  )

  const handleApplyRecent = useCallback(
    (recent) => {
      if (!recent) return
      applyQueryState(recent.query || {})
    },
    [applyQueryState]
  )

  const handleInputChange = (event) => {
    setQuery(event.target.value)
    setPage(1)
  }

  const handleInputKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((prev) => {
        const next = Math.min((prev < 0 ? 0 : prev + 1), results.length - 1)
        return next
      })
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((prev) => {
        const next = prev <= 0 ? -1 : prev - 1
        return next
      })
    } else if (event.key === 'Enter') {
      if (results.length === 0) return
      event.preventDefault()
      const index = activeIndex >= 0 && activeIndex < results.length ? activeIndex : 0
      handleSelectResult(results[index])
    }
  }

  const handleAddTag = useCallback(() => {
    const normalized = normalizeTag(tagDraft)
    setTagDraft('')
    if (!normalized) return
    setTags((prev) => {
      if (prev.some((tag) => tag.toLowerCase() === normalized.toLowerCase())) {
        return prev
      }
      return [...prev, normalized]
    })
    setPage(1)
  }, [tagDraft])

  const handleTagInputKeyDown = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      handleAddTag()
    }
  }

  const handleRemoveTag = (tag) => {
    setTags((prev) => prev.filter((item) => item !== tag))
    setPage(1)
  }

  const handleBookChange = (event) => {
    setBook(event.target.value)
    setPage(1)
  }

  const handleRangeSelect = (key) => {
    setRangeKey(key)
    setPage(1)
  }

  const handleClearFilters = () => {
    setTags([])
    setTagDraft('')
    setBook('')
    setRangeKey('any')
    setPage(1)
  }

  const handleOverlayClick = (event) => {
    if (event.target === event.currentTarget && onClose) {
      onClose()
    }
  }

  const handleLoadMore = () => {
    if (nextPage) {
      setPage(nextPage)
    }
  }

  if (!open) {
    return null
  }

  return (
    <div className="instant-search" role="presentation">
      <div className="instant-search__overlay" onMouseDown={handleOverlayClick}>
        <div className="instant-search__panel" role="dialog" aria-modal="true">
          <header className="instant-search__header">
            <div className="instant-search__input-row">
              <input
                ref={inputRef}
                type="search"
                className="instant-search__input"
                placeholder="Type to find snippets…"
                value={query}
                onChange={handleInputChange}
                onKeyDown={handleInputKeyDown}
                aria-label="Search snippets"
                autoFocus
              />
              <button type="button" className="instant-search__close" onClick={onClose}>
                Esc
              </button>
            </div>
            <div className="instant-search__chips" role="group" aria-label="Quick filters">
              {QUICK_RANGES.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className={`instant-search__chip ${rangeKey === option.key ? 'is-active' : ''}`}
                  onClick={() => handleRangeSelect(option.key)}
                >
                  {option.label}
                </button>
              ))}
              {(tags.length > 0 || trimmedBook || rangeKey !== 'any') && (
                <button type="button" className="instant-search__chip clear" onClick={handleClearFilters}>
                  Clear filters
                </button>
              )}
            </div>
            <div className="instant-search__filters">
              <div className="instant-search__filter-group">
                <label className="instant-search__filter-label" htmlFor="instant-search-tag-input">
                  Tags
                </label>
                <div className="instant-search__tag-editor">
                  {tags.map((tag) => (
                    <span key={tag} className="instant-search__tag">
                      #{tag}
                      <button
                        type="button"
                        className="instant-search__tag-remove"
                        onClick={() => handleRemoveTag(tag)}
                        aria-label={`Remove tag ${tag}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  <input
                    id="instant-search-tag-input"
                    type="text"
                    className="instant-search__tag-input"
                    placeholder="Add tag"
                    value={tagDraft}
                    onChange={(event) => setTagDraft(event.target.value)}
                    onKeyDown={handleTagInputKeyDown}
                    onBlur={handleAddTag}
                  />
                </div>
              </div>
              <div className="instant-search__filter-group">
                <label className="instant-search__filter-label" htmlFor="instant-search-book-input">
                  Book
                </label>
                <input
                  id="instant-search-book-input"
                  type="text"
                  className="instant-search__text-input"
                  placeholder="Filter by book title"
                  value={book}
                  onChange={handleBookChange}
                />
              </div>
              {user && (
                <div className="instant-search__actions">
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-light"
                    onClick={handleSaveSearch}
                    disabled={!hasCriteria}
                  >
                    Save search
                  </button>
                </div>
              )}
            </div>
          </header>

          <div className="instant-search__content">
            <div className="instant-search__results" role="listbox">
              {error ? <div className="instant-search__error">{error}</div> : null}
              {!error && loading && results.length === 0 ? (
                <div className="instant-search__status">Searching…</div>
              ) : null}
              {!error && !loading && results.length === 0 && hasCriteria ? (
                <div className="instant-search__status">
                  <p>No matches yet. Try refining your filters or checking a different time range.</p>
                </div>
              ) : null}
              {!error && !hasCriteria ? (
                <div className="instant-search__status">
                  <p>Start typing to search across snippet text and thoughts.</p>
                  <p className="instant-search__hint">Use tags, book titles, and time ranges to narrow results.</p>
                </div>
              ) : null}
              <ul className="instant-search__result-list">
                {results.map((item, index) => {
                  const isActive = index === activeIndex
                  const createdAt = item.created_utc ? new Date(item.created_utc) : null
                  const createdLabel = createdAt ? createdAt.toLocaleDateString() : ''
                  return (
                    <li key={item.id} className={`instant-search__result ${isActive ? 'is-active' : ''}`}>
                      <button
                        type="button"
                        className="instant-search__result-button"
                        onClick={() => handleSelectResult(item)}
                        onMouseEnter={() => setActiveIndex(index)}
                      >
                        <div className="instant-search__result-header">
                          <div>
                            <div className="instant-search__result-title">{item.book_name || 'Untitled'}</div>
                            <div className="instant-search__result-meta">
                              {item.created_by_username ? <span>by {item.created_by_username}</span> : null}
                              {createdLabel ? <span> · {createdLabel}</span> : null}
                            </div>
                          </div>
                          {item.tags && item.tags.length > 0 ? (
                            <div className="instant-search__result-tags">
                              {item.tags.slice(0, 3).map((tag) => (
                                <span key={tag.id} className="instant-search__result-tag">
                                  #{tag.name}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                        {item.highlights?.text ? (
                          <div
                            className="instant-search__result-snippet"
                            dangerouslySetInnerHTML={{ __html: item.highlights.text }}
                          />
                        ) : null}
                        {item.highlights?.thoughts ? (
                          <div
                            className="instant-search__result-thoughts"
                            dangerouslySetInnerHTML={{ __html: item.highlights.thoughts }}
                          />
                        ) : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
              {nextPage && !loading ? (
                <button type="button" className="instant-search__load-more" onClick={handleLoadMore}>
                  Show more results
                </button>
              ) : null}
              {total > 0 ? (
                <div className="instant-search__summary">{total.toLocaleString()} results</div>
              ) : null}
            </div>

            <aside className="instant-search__sidebar">
              {user ? (
                <section className="instant-search__section">
                  <h2 className="instant-search__section-title">Saved searches</h2>
                  {savedSearches.length === 0 ? (
                    <p className="instant-search__hint">No saved searches yet. Save one from an active query.</p>
                  ) : (
                    <ul className="instant-search__saved-list">
                      {savedSearches.map((search) => (
                        <li key={search.id} className="instant-search__saved-item">
                          <button
                            type="button"
                            className="instant-search__saved-button"
                            onClick={() => handleApplySaved(search)}
                          >
                            {search.name}
                          </button>
                          <div className="instant-search__saved-actions">
                            <button type="button" onClick={() => handleRenameSearch(search)}>
                              Rename
                            </button>
                            <button type="button" onClick={() => handleDeleteSearch(search)}>
                              Delete
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ) : null}

              <section className="instant-search__section">
                <h2 className="instant-search__section-title">Recent searches</h2>
                {recentSearches.length === 0 ? (
                  <p className="instant-search__hint">Your most recent searches will appear here.</p>
                ) : (
                  <ul className="instant-search__saved-list">
                    {recentSearches.map((entry, index) => (
                      <li key={`${entry.query.q}-${index}`} className="instant-search__saved-item">
                        <button
                          type="button"
                          className="instant-search__saved-button"
                          onClick={() => handleApplyRecent(entry)}
                        >
                          {entry.query.q || entry.query.book || entry.query.tags?.join(', ') || 'Untitled search'}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>
        </div>
      </div>
    </div>
  )
}