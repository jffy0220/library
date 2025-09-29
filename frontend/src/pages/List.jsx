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
import { useAddSnippet } from '../components/AddSnippetProvider'

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
  const trendingCommentTotal = trending.reduce((total, item) => total + (item.recent_comment_count || 0), 0)

  return (
    <div className="home-page">
      {!user && (
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
              Build a feed inspired by your favorite communities on Facebook, X, and Reddit. Follow what the
              library is reading, remix tags, and bring new color to the conversation.
            </p>
            <div className="home-hero__actions">
              {user ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={openAddSnippet}
                  aria-keyshortcuts="Control+K Meta+K"
                >
                  Share a snippet
                </button>
              ) : (
                <Link className="btn btn-primary" to="/register">
                  Join the library
                </Link>
              )}
              <Link className="btn btn-outline-light" to={user ? '/groups' : '/login'}>
                {user ? 'Browse your groups' : 'Preview the feed'}
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

      <div className="home-layout">
        <div className="home-layout__main d-flex flex-column gap-4">
          <section className="filter-panel">
            <div className="filter-panel__header">
              <h2 className="filter-panel__title">Discover snippets</h2>
              <div className="filter-panel__sort">
                <label className="form-label mb-0" htmlFor="snippet-sort">
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
            <div>
              <SearchBar value={q} onSearch={(next) => updateSearchParams({ q: next, page: 1 })} />
              <div className="search-help">Search across snippet text and reflections.</div>
            </div>
            <div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h6 className="mb-0 text-uppercase text-muted" style={{ letterSpacing: '0.08em' }}>
                  Filter by tag
                </h6>
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
          </section>

          <section className="snippet-feed">
            <div className="snippet-feed__header">
              <div className="snippet-feed__summary">{summaryText}</div>
              <div className="snippet-feed__meta">
                {hasVisibleResults ? (
                  <span>
                    Showing {showingRangeStart}-{showingRangeEnd} · Page {page}
                  </span>
                ) : null}
                {q ? <span>Keyword: “{q}”</span> : null}
                {selectedTags.length > 0 ? <span>Tags: {selectedTags.join(', ')}</span> : null}
              </div>
            </div>

            <div className="d-flex flex-column gap-3">
              {error ? <div className="alert alert-danger mb-0">{error}</div> : null}
              {!error && loading && rows.length === 0 ? (
                <div className="snippet-card text-muted">Loading feed…</div>
              ) : null}
              {!loading && !error && rows.length === 0 ? (
                <div className="snippet-card text-muted">No snippets found. Try adjusting your filters.</div>
              ) : null}
              {!error && rows.length > 0
                ? rows.map((r) => {
                    const preview = (r.text_snippet || '').slice(0, 280)
                    const showEllipsis = r.text_snippet && r.text_snippet.length > 280
                    const visibility = (r.visibility || '').toLowerCase()
                    const isPrivate = visibility === 'private'
                    return (
                      <article key={r.id} className="snippet-card">
                        <div className="snippet-card__header">
                          <div>
                            <h3 className="snippet-card__title">
                              <Link to={`/snippet/${r.id}`}>{r.book_name || 'Untitled'}</Link>
                            </h3>
                            <div className="snippet-card__meta">
                              {r.created_by_username ? <span>by {r.created_by_username}</span> : null}
                              {r.page_number != null ? <span>p. {r.page_number}</span> : null}
                              {r.chapter ? <span>ch. {r.chapter}</span> : null}
                              {r.verse ? <span>v. {r.verse}</span> : null}
                              {isPrivate ? (
                                <span className="badge text-bg-warning ms-2">Private</span>
                              ) : null}
                            </div>
                          </div>
                          <span className="snippet-card__timestamp">
                            {new Date(r.created_utc).toLocaleString()}
                          </span>
                        </div>
                        <div className="snippet-card__body">
                          {preview}
                          {showEllipsis ? '…' : ''}
                        </div>
                        {r.tags && r.tags.length > 0 ? (
                          <div className="snippet-card__tags">
                            {r.tags.map((tag) => (
                              <button
                                key={tag.id}
                                type="button"
                                className="snippet-card__tag"
                                onClick={() => handleAddTagFilter(tag.name)}
                              >
                                #{tag.name}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </article>
                    )
                  })
                : null}
              {loading && !error && rows.length > 0 ? (
                <div className="snippet-card text-muted d-flex align-items-center gap-2">
                  <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                  <span>Updating results…</span>
                </div>
              ) : null}
            </div>

            {!error && totalCount > 0 ? (
              <div className="snippet-feed__footer">
                <span>
                  {hasVisibleResults
                    ? `Showing ${showingRangeStart}-${showingRangeEnd} of ${totalCount} snippet${totalCount === 1 ? '' : 's'}`
                    : `No snippets on this page. Total results: ${totalCount}`}
                </span>
                <div className="d-flex align-items-center gap-2 flex-wrap">
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
          </section>
        </div>

        <aside className="sidebar-panel">
          <div className="sidebar-card">
            <h3 className="sidebar-card__title">Popular tags this week</h3>
            {sidebarLoading ? (
              <div>Loading…</div>
            ) : sidebarError ? (
              <div className="text-muted small">{sidebarError}</div>
            ) : popularTags.length === 0 ? (
              <div className="text-muted small">No trending tags yet.</div>
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

          <div className="sidebar-card">
            <h3 className="sidebar-card__title">Popular this week</h3>
            {sidebarLoading ? (
              <div>Loading…</div>
            ) : trending.length === 0 ? (
              <div className="text-muted small">No trending snippets yet.</div>
            ) : (
              <div className="trending-list">
                {trending.map((item) => (
                  <div key={item.id} className="trending-item">
                    <div className="d-flex justify-content-between align-items-center gap-2">
                      <Link to={`/snippet/${item.id}`} className="fw-semibold">
                        {item.book_name || 'Untitled'}
                      </Link>
                      <span className="badge bg-secondary">
                        {item.recent_comment_count} comment{item.recent_comment_count === 1 ? '' : 's'}
                      </span>
                    </div>
                    <div className="trending-item__meta">
                      {item.tag_count} tag{item.tag_count === 1 ? '' : 's'} · {item.lexeme_count} terms
                    </div>
                    {item.tags && item.tags.length ? (
                      <div className="popular-tag-list">
                        {item.tags.slice(0, 4).map((tag) => (
                          <button
                            key={`${item.id}-${tag.id}`}
                            type="button"
                            className="tag-chip tag-chip--outlined"
                            onClick={() => handleAddTagFilter(tag.name)}
                          >
                            #{tag.name}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
