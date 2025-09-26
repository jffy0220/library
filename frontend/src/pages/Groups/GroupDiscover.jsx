import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { discoverGroups } from '../../api'

const PRIVACY_DESCRIPTIONS = {
  public: 'Discoverable by everyone in the library. Join to see member posts',
  unlisted: 'Hidden from discovery, but accessible to anyone with the link.',
  private: 'Only members can view posts and discussions.',
}

const normalizePrivacy = (value) => {
  if (!value) return 'public'
  if (typeof value === 'string') return value.trim().toLowerCase()
  return 'public'
}

function GroupPrivacyBadge({ privacy }) {
  const normalized = normalizePrivacy(privacy)
  const variant = normalized === 'private' ? 'danger' : normalized === 'unlisted' ? 'secondary' : 'success'
  return (
    <span className={`badge text-bg-${variant}`} data-testid={`privacy-${normalized}`}>
      {normalized.charAt(0).toUpperCase() + normalized.slice(1)}
    </span>
  )
}

export default function GroupDiscover() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [pendingQuery, setPendingQuery] = useState('')

  const loadGroups = async (options = {}) => {
    setLoading(true)
    setError(null)
    try {
      const data = await discoverGroups({
        q: options.query ?? (query || undefined),
        visibility: ['public', 'unlisted'],
        limit: 50,
      })
      const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []
      setGroups(items)
    } catch (err) {
      console.error('Failed to load groups', err)
      const detail = err?.response?.data?.detail
      let message = 'Unable to load groups right now.'
      if (detail) {
        if (typeof detail === 'string') {
          message = detail
        } else if (Array.isArray(detail)) {
          const parts = detail
            .map((item) => {
              if (!item) return null
              if (typeof item === 'string') return item
              if (typeof item === 'object') return item.msg || item.detail || null
              return null
            })
            .filter(Boolean)
          if (parts.length > 0) {
            message = parts.join(' ')
          }
        } else if (typeof detail === 'object') {
          message = detail.msg || detail.detail || message
        }
      }
      setError(message)
      setGroups([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGroups()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setQuery(pendingQuery)
    await loadGroups({ query: pendingQuery })
  }

  const resultsSummary = useMemo(() => {
    if (loading && groups.length === 0) return 'Loading discoverable groups…'
    const count = groups.length
    if (count === 0) {
      return query ? 'No groups matched your search.' : 'No discoverable groups yet.'
    }
    return `${count} discoverable group${count === 1 ? '' : 's'}`
  }, [groups.length, loading, query])

  return (
    <div className="groups-discover" data-testid="groups-discover">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h2 className="h4 mb-0">Discover groups</h2>
        <span className="text-muted small">{resultsSummary}</span>
      </div>
      <form className="card card-body mb-4" onSubmit={handleSubmit}>
        <label className="form-label" htmlFor="discover-groups-query">
          Search for a group by name or keyword
        </label>
        <div className="input-group">
          <input
            id="discover-groups-query"
            className="form-control"
            placeholder="Search groups"
            value={pendingQuery}
            onChange={(event) => setPendingQuery(event.target.value)}
          />
          <button className="btn btn-outline-secondary" type="submit" disabled={loading && pendingQuery === query}>
            Search
          </button>
        </div>
      </form>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading && groups.length === 0 ? (
        <div className="text-center py-5">Loading discoverable groups…</div>
      ) : groups.length === 0 ? (
        <div className="text-center py-5 text-muted" data-testid="groups-empty">
          No discoverable groups yet. Check back soon or ask a moderator to create one.
        </div>
      ) : (
        <div className="row gy-3" data-testid="groups-results">
          {groups.map((group) => {
            const privacy = normalizePrivacy(group.privacy_state || group.privacyState)
            const slug = group.slug || String(group.id)
            const inviteOnly = Boolean(group.invite_only ?? group.inviteOnly)
            return (
              <div className="col-md-6" key={`${group.id}-${slug}`}>
                <div className="card h-100 shadow-sm">
                  <div className="card-body d-flex flex-column">
                    <div className="d-flex justify-content-between align-items-start mb-2">
                      <h3 className="h5 mb-0">{group.name}</h3>
                      <div className="d-flex align-items-center gap-2">
                        <GroupPrivacyBadge privacy={privacy} />
                        {inviteOnly && (
                          <span className="badge text-bg-warning" title="Invitation required to join">
                            Invite only
                          </span>
                        )}
                      </div>
                    </div>
                    {group.description && <p className="flex-grow-1 text-muted">{group.description}</p>}
                    <p className="text-muted small mb-3">
                      {PRIVACY_DESCRIPTIONS[privacy] || PRIVACY_DESCRIPTIONS.public}
                    </p>
                    <Link className="btn btn-outline-primary mt-2" to={`/groups/${slug}`}>
                      View feed
                    </Link>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}