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

export default function List() {
  const [ searchParams, setSearchParams ] = useSearchParams();
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [availableTags, setAvailableTags] = useState([])
  const [popularTags, setPopularTags] = useState([])
  const [trending, setTrending] = useState([])
  const [sidebarLoading, setSidebarLoading] = useState(true)
  const [sidebarError, setSidebarError] = useState(null)

  const q = searchParams.get('q') || ''
  const sort = searchParams.get('sort') || 'recent'
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

  const updateSearchParams = (updates) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if ('q' in updates) {
        const nextQ = updates.q?.trim()
        if (nextQ) next.set('q', nextQ)
        else next.delete('q')
      }
      if ('sort' in updates) {
        const nextSort = updates.sort
        if (nextSort && nextSort !== 'recent') next.set('sort', nextSort)
        else next.delete('sort')
      }
      if ('tags' in updates) {
        next.delete('tag')
        next.delete('tags')
        const tagList = (updates.tags || [])
          .map((tag) => tag.trim())
          .filter(Boolean)
        tagList.forEach((tag) => next.append('tag', tag))
      }
      return next
    })
  }

  const handleAddTagFilter = (tagName) => {
    const normalized = (tagName || '').trim()
    if (!normalized) return
    if (selectedTags.some((tag) => tag.toLowerCase() === normalized.toLowerCase())) return
    updateSearchParams({ tags: [...selectedTags, normalized] })
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
        })
        if (!ignore) setRows(data)
      } catch (err) {
        if (!ignore && err?.response?.status !== 401) {
          console.error('Failed to load snippets', err)
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    })()
    return () => { ignore = true }
  }, [q, sort, tagsKey])

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

  if (loading) return <div>Loading…</div>

  return (
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
                onChange={(event) => updateSearchParams({ sort: event.target.value })}
              >
                <option value="recent">Most recent</option>
                <option value="trending">Trending</option>
              </select>
            </div>
          </div>
          <div className="card-body d-flex flex-column gap-4">
            <div>
              <SearchBar value={q} onSearch={(next) => updateSearchParams({ q: next })} />
              <small className="text-muted">Search across snippet text and reflections.</small>
            </div>
            <div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h6 className="mb-0">Filter by tag</h6>
                {selectedTags.length > 0 ? (
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0"
                    onClick={() => updateSearchParams({ tags: [] })}
                  >
                    Clear tags
                  </button>
                ) : null}
              </div>
              <TagSelector
                availableTags={availableTags}
                value={selectedTags}
                onChange={(next) => updateSearchParams({ tags: next })}
                showCounts
              />
            </div>
          </div>
        </div>

        <div className="card shadow-sm">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>
              {loading ? 'Loading snippets…' : `${rows.length} hit${rows.length === 1 ? '' : 's'}`}
            </span>
            {q ? <span className="text-muted small">Keyword: “{q}”</span> : null}
          </div>
          <div className="list-group list-group-flush">
            {error ? <div className="list-group-item text-danger">{error}</div> : null}
            {!error && loading ? <div className="list-group-item">Loading…</div> : null}
            {!loading && !error && rows.length === 0 ? (
              <div className="list-group-item text-muted">No snippets found. Try adjusting your filters.</div>
            ) : null}
            {!loading && !error
              ? rows.map((r) => (
                  <div key={r.id} className="list-group-item">
                    <div className="d-flex w-100 justify-content-between align-items-start flex-wrap gap-2">
                      <div>
                        <h6 className="mb-1">
                          <Link to={`/snippet/${r.id}`}>{r.book_name || 'Untitled'}</Link>
                        </h6>
                        <div className="text-muted small">
                          {r.created_by ? <>by {r.created_by}</> : null}
                          {r.created_by && (r.page_number != null || r.chapter || r.verse) ? ' · ' : ''}
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
  )
}
