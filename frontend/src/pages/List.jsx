import React, { useEffect, useState, useMemo } from 'react'
import {
  listSnippets,
  listTags,
  listPopularTags,
  getTrendingSnippets,
} from '../api'
import SearchBar from '../components/SearchBar'
import TagSelector from '../components/TagSelector'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'

const PAGE_SIZE = 20

export default function List() {
  const { user } = useAuth()
  const [ searchParams, setSearchParams ] = useSearchParams();
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [meta, setMeta] = useState({ total: 0, nextPage: null })
  const [availableTags, setAvailableTags] = useState([])
  const [popularTags, setPopularTags] = useState([])
  const [trending, setTrending] = useState([])
  const [sidebarLoading, setSidebarLoading] = useState(true)
  const [sidebarError, setSidebarError] = useState(null)
  const [pendingPage, setPendingPage] = useState(null)

  const q = searchParams.get('q') || ''
  const sort = searchParams.get('sort') || 'recent'
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

  const updateSearchParams = (updates, options = {}) => {
    const { preservePendingPage = false } = options
    if (!preservePendingPage) {
      setPendingPage(null)
    }
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
  }

  const handleAddTagFilter = (tagName) => {
    const normalized = (tagName || '').trim()
    if (!normalized) return
    if (selectedTags.some((tag) => tag.toLowerCase() === normalized.toLowerCase())) return
    updateSearchParams({ tags: [...selectedTags, normalized], page: 1 })
  }

  const goToPage = (nextPageValue) => {
    const target = Math.max(1, Number.parseInt(nextPageValue, 10) || 1)
    if (target === page) return
    setPendingPage(target)
    updateSearchParams({ page: target }, { preservePendingPage: true })
  }

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const data = await listSnippets({
          q: q || undefined,
          tags: selectedTags,
          sort,
          limit: PAGE_SIZE,
          page,
        })
        if (!ignore) {
          const items = Array.isArray(data?.items) ? data.items : []
          setRows(items)
          setMeta({
            total: typeof data?.total === 'number' ? data.total : items.length,
            nextPage: typeof data?.nextPage === 'number' ? data.nextPage : null,
          })
        }
      } catch (err) {
        if (!ignore && err?.response?.status !== 401) {
          if (err?.response?.status === 401) {
            return
          }
          console.error('Failed to load snippets', err)
          const detail = err?.response?.data?.detail
          setError(detail || 'Failed to load snippets.')
          setRows([])
          setMeta({ total: 0, nextPage: null })
        }
      } finally {
        if (!ignore) {
          setLoading(false)
          setPendingPage(null)
        }
      }
    })()
    return () => { ignore = true }
  }, [q, sort, tagsKey, page])

  useEffect(() => {
    let ignore = false
    setSidebarLoading(true)
    setSidebarError(null)
    ;(async () => {
      try {
        const [allTags, popular, trendingSnippets] = await Promise.all([
          listTags({ limit: 200 }),
          listPopularTags({ days: 7, limit: 12 }),
          getTrendingSnippets({ limit: 6 }),
        ])
        if (!ignore) {
          setAvailableTags(allTags)
          setPopularTags(popular)
          setTrending(trendingSnippets)
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

  const totalCount = meta.total || 0
  const nextPageNumber = typeof meta.nextPage === 'number' ? meta.nextPage : null
  const hasPreviousPage = page > 1
  const hasNextPage = nextPageNumber != null
  const hasVisibleResults = !error && rows.length > 0
  const showingRangeStart = hasVisibleResults && totalCount > 0 ? (page - 1) * PAGE_SIZE + 1 : 0
  const showingRangeEnd = hasVisibleResults && totalCount > 0
    ? Math.min((page - 1) * PAGE_SIZE + rows.length, totalCount)
    : 0
  const summaryText = loading && rows.length === 0
    ? 'Loading snippets…'
    : `${totalCount} snippet${totalCount === 1 ? '' : 's'} found`
  const isPaginating = pendingPage !== null && loading

  return (
    <>
      {!user && (
        <div className="alert alert-info">
          Want to share your own discoveries?{' '}
          <Link to="/login" className="alert-link">
            Sign In
          </Link>{' '}
          to contribute snippets and join the discussion.
        </div>
      )}
      <div className="row g-4">
        <div className="col-lg-8">
          <div className="card shadow-sm mb-4">
            <div className="card-header d-flex flex-column flex-lg-row gap-2 gap-lg-3 justify-content-between align-items-lg-center">
              <h5 className="mb-0">Discover snippets</h5>
              <div className="d-flex align-items-center gap-2">
                <label className="form-label mb-0 text-muted" htmlFor="snippet-sort">
                  Sort by
                </label>
                <select
                  id="snippet-sort"
                  className="form-select form-select-sm w-auto"
                  value={sort}
                  onChange={(event) => updateSearchParams({ sort: event.target.value, page: 1 })}
                >
                  <option value="recent">Most recent</option>
                  <option value="trending">Trending</option>
                </select>
              </div>
            </div>
            <div className="card-body d-flex flex-column gap-4">
              <div>
                <SearchBar value={q} onSearch={(next) => updateSearchParams({ q: next, page: 1 })} />
                <small className="text-muted">Search across snippet text and reflections.</small>
              </div>
              <div>
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <h6 className="mb-0">Filter by tag</h6>
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
            </div>
          </div>

          <div className="card shadow-sm">
            <div className="card-header d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-2">
              <div className="d-flex flex-column">
                <span>{summaryText}</span>
                {hasVisibleResults ? (
                  <small className="text-muted">
                    Showing {showingRangeStart}-{showingRangeEnd} · Page {page}
                  </small>
                ) : null}
              </div>
              <div className="d-flex flex-column align-items-md-end">
                {q ? <span className="text-muted small">Keyword: “{q}”</span> : null}
                {selectedTags.length > 0 ? (
                  <span className="text-muted small">
                    Tags: {selectedTags.join(', ')}
                  </span>
                ) : null}
              </div>
            <div className="list-group list-group-flush">
              {error ? <div className="list-group-item text-danger">{error}</div> : null}
              {!error && loading && rows.length === 0 ? (
                <div className="list-group-item">Loading…</div>
              ) : null}
              {!loading && !error && rows.length === 0 ? (
                <div className="list-group-item text-muted">No snippets found. Try adjusting your filters.</div>
              ) : null}
              {!error && rows.length > 0
                ? rows.map((r) => (
                    <div key={r.id} className="list-group-item">
                      <div className="d-flex w-100 justify-content-between align-items-start flex-wrap gap-2">
                        <div>
                          <h6 className="mb-1">
                            <Link to={`/snippet/${r.id}`}>{r.book_name || 'Untitled'}</Link>
                          </h6>
                          <div className="text-muted small">
                            {r.created_by_username ? <>by {r.created_by_username}</> : null}
                            {r.created_by_username && (r.page_number != null || r.chapter || r.verse) ? ' · ' : ''}
                            {r.page_number != null ? <>p. {r.page_number}</> : null}
                            {r.chapter ? <>{r.page_number != null ? ' · ' : ''}ch. {r.chapter}</> : null}
                            {r.verse ? <>{(r.page_number != null || r.chapter) ? ' · ' : ''}v. {r.verse}</> : null}
                          </div>
                        </div>
                        <small className="text-muted">{new Date(r.created_utc).toLocaleString()}</small>
                      </div>
                      <div className="mt-2" style={{ whiteSpace: 'pre-line' }}>
                        {(r.text_snippet || '').slice(0, 240)}
                        {r.text_snippet && r.text_snippet.length > 240 ? '…' : ''}
                      </div>
                      {r.tags && r.tags.length > 0 ? (
                        <div className="mt-3 d-flex flex-wrap gap-2">
                          {r.tags.map((tag) => (
                            <button
                              key={tag.id}
                              type="button"
                              className="btn btn-sm btn-outline-secondary"
                              onClick={() => handleAddTagFilter(tag.name)}
                            >
                              #{tag.name}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))
                : null}
                {loading && !error && rows.length > 0 ? (
                <div className="list-group-item text-muted d-flex align-items-center gap-2">
                  <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                  <span>Updating results…</span>
                </div>
              ) : null}
            </div>
            {!error && totalCount > 0 ? (
              <div className="card-footer d-flex flex-column flex-md-row gap-3 justify-content-between align-items-md-center">
                <small className="text-muted">
                  {hasVisibleResults
                    ? (
                      <>Showing {showingRangeStart}-{showingRangeEnd} of {totalCount} snippet{totalCount === 1 ? '' : 's'}</>
                    ) : (
                      <>No snippets on this page. Total results: {totalCount}</>
                    )}
                </small>
                <div className="d-flex align-items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-outline-secondary btn-sm"
                    disabled={!hasPreviousPage || loading}
                    onClick={() => hasPreviousPage && goToPage(page - 1)}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline-secondary btn-sm"
                    disabled={!hasNextPage || loading}
                    onClick={() => hasNextPage && goToPage(nextPageNumber)}
                  >
                    Next
                  </button>
                  {isPaginating ? (
                    <span className="text-muted d-flex align-items-center gap-2">
                      <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                      <span>Loading page…</span>
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}
            </div>
          </div>
        </div>

        <div className="col-lg-4">
          <div className="card shadow-sm mb-4">
            <div className="card-header">Popular tags this week</div>
            <div className="card-body">
              {sidebarLoading ? (
                <div>Loading…</div>
              ) : sidebarError ? (
                <div className="text-muted small">{sidebarError}</div>
              ) : popularTags.length === 0 ? (
                <div className="text-muted small">No trending tags yet.</div>
              ) : (
                <div className="d-flex flex-wrap gap-2">
                  {popularTags.map((tag) => (
                    <button
                      key={tag.id}
                      type="button"
                      className="btn btn-sm btn-outline-secondary"
                      onClick={() => handleAddTagFilter(tag.name)}
                    >
                      #{tag.name}
                      {typeof tag.usage_count === 'number' ? (
                        <span className="badge bg-light text-dark ms-1">{tag.usage_count}</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="card shadow-sm">
            <div className="card-header">Popular this week</div>
            <div className="list-group list-group-flush">
              {sidebarLoading ? (
                <div className="list-group-item">Loading…</div>
              ) : trending.length === 0 ? (
                <div className="list-group-item text-muted">No trending snippets yet.</div>
              ) : (
                trending.map((item) => (
                  <div key={item.id} className="list-group-item">
                    <div className="d-flex justify-content-between align-items-center">
                      <Link to={`/snippet/${item.id}`} className="fw-semibold">
                        {item.book_name || 'Untitled'}
                      </Link>
                      <span className="badge bg-secondary">
                        {item.recent_comment_count} comment{item.recent_comment_count === 1 ? '' : 's'}
                      </span>
                    </div>
                    <div className="text-muted small mt-1">
                      {item.tag_count} tag{item.tag_count === 1 ? '' : 's'} · {item.lexeme_count} terms
                    </div>
                    {item.tags && item.tags.length ? (
                      <div className="mt-2 d-flex flex-wrap gap-2">
                        {item.tags.slice(0, 4).map((tag) => (
                          <button
                            key={`${item.id}-${tag.id}`}
                            type="button"
                            className="btn btn-sm btn-outline-secondary"
                            onClick={() => handleAddTagFilter(tag.name)}
                          >
                            #{tag.name}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </>
    
  )
}
