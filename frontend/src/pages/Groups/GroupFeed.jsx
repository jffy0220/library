import React, { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getGroup,
  getGroupBySlug,
  listGroupSnippets,
  listMyGroupMemberships,
} from '../../api'
import { useAuth } from '../../auth'

const PAGE_SIZE = 10

const normalizePrivacy = (value) => {
  if (!value) return 'public'
  if (typeof value === 'string') return value.trim().toLowerCase()
  return 'public'
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}

function GroupHeader({ group, membershipRole, canManage }) {
  const privacy = normalizePrivacy(group?.privacy_state || group?.privacyState)
  return (
    <div className="card shadow-sm mb-4" data-testid="group-header">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start flex-wrap gap-3">
          <div>
            <h2 className="h4 mb-1">{group?.name}</h2>
            <div className="text-muted small">{privacy === 'private' ? 'Private group' : privacy === 'unlisted' ? 'Unlisted group' : 'Public group'}</div>
          </div>
          {canManage && (
            <Link className="btn btn-outline-secondary" to={`/groups/${group.slug || group.id}/manage`}>
              Manage members
            </Link>
          )}
        </div>
        {group?.description && <p className="mb-0 mt-3">{group.description}</p>}
        {membershipRole && (
          <p className="text-muted small mb-0" data-testid="group-membership-role">
            You are a {membershipRole} of this group.
          </p>
        )}
      </div>
    </div>
  )
}

function SnippetCard({ snippet }) {
  const createdAt = formatDate(snippet.created_utc || snippet.createdUtc)
  const author = snippet.created_by_username || snippet.createdByUsername
  const snippetText = snippet.text_snippet || snippet.textSnippet || ''
  return (
    <div className="card shadow-sm mb-3" data-testid="group-snippet">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-center mb-2">
          <div className="fw-semibold">{snippet.book_name || snippet.bookName || 'Untitled selection'}</div>
          {createdAt && <span className="text-muted small">{createdAt}</span>}
        </div>
        <p className="mb-2">{snippetText}</p>
        <div className="d-flex justify-content-between align-items-center">
          <span className="text-muted small">Posted by {author || 'Anonymous reader'}</span>
          <Link className="btn btn-sm btn-outline-primary" to={`/snippet/${snippet.id}`}>
            View snippet
          </Link>
        </div>
      </div>
    </div>
  )
}

export default function GroupFeed() {
  const { groupSlug } = useParams()
  const { user } = useAuth()
  const [group, setGroup] = useState(null)
  const [membershipRole, setMembershipRole] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [snippets, setSnippets] = useState([])
  const [meta, setMeta] = useState({ total: 0, nextPage: null })
  const [loadingMore, setLoadingMore] = useState(false)

  const loadGroupDetail = async (slugValue) => {
    if (!slugValue) throw new Error('Missing group identifier')
    const slugText = String(slugValue)
    const numericId = Number.parseInt(slugText, 10)
    if (!Number.isNaN(numericId)) {
      try {
        const detailById = await getGroup(numericId)
        if (detailById) return detailById
      } catch (err) {
        if (err?.response?.status !== 404) throw err
      }
    }
    try {
      return await getGroupBySlug(slugText)
    } catch (err) {
      if (numericId && err?.response?.status === 404) {
        return getGroup(numericId)
      }
      throw err
    }
  }

  const refreshFeed = async (slugValue) => {
    setLoading(true)
    setError(null)
    setSnippets([])
    setMeta({ total: 0, nextPage: null })
    try {
      const detail = await loadGroupDetail(slugValue)
      setGroup(detail)
      const feed = await listGroupSnippets(detail.id, { limit: PAGE_SIZE, page: 1 })
      const items = Array.isArray(feed?.items) ? feed.items : []
      setSnippets(items)
      setMeta({
        total: typeof feed?.total === 'number' ? feed.total : items.length,
        nextPage: feed?.nextPage ?? null,
      })
      try {
        const memberships = await listMyGroupMemberships()
        if (Array.isArray(memberships)) {
          const match = memberships.find((m) => {
            const nestedGroup = m.group || {}
            const membershipGroupId =
              m.group_id ?? m.groupId ?? nestedGroup.id ?? (typeof m.id === 'number' ? m.id : null)
            if (membershipGroupId === detail.id) return true
            const membershipSlug = m.slug || nestedGroup.slug
            return membershipSlug && detail.slug && membershipSlug === detail.slug
          })
          setMembershipRole(match?.role || match?.group_role || match?.membershipRole || null)
        } else {
          setMembershipRole(null)
        }
      } catch (membershipError) {
        if (membershipError?.response?.status !== 403) {
          console.warn('Unable to load membership list', membershipError)
        }
        setMembershipRole(null)
      }
    } catch (err) {
      console.error('Failed to load group feed', err)
      const status = err?.response?.status
      if (status === 404) {
        setError('Group not found.')
      } else if (status === 403) {
        setError('You do not have access to this group feed.')
      } else {
        const detail = err?.response?.data?.detail
        setError(detail || 'Unable to load group feed.')
      }
      setGroup(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshFeed(groupSlug)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupSlug])

  const loadMore = async () => {
    if (!group || !meta.nextPage) return
    setLoadingMore(true)
    try {
      const feed = await listGroupSnippets(group.id, { limit: PAGE_SIZE, page: meta.nextPage })
      const items = Array.isArray(feed?.items) ? feed.items : []
      setSnippets((prev) => [...prev, ...items])
      setMeta({
        total: typeof feed?.total === 'number' ? feed.total : meta.total,
        nextPage: feed?.nextPage ?? null,
      })
    } catch (err) {
      console.error('Failed to load more snippets', err)
      const detail = err?.response?.data?.detail
      setError(detail || 'Unable to load more snippets.')
    } finally {
      setLoadingMore(false)
    }
  }

  const canManage = useMemo(() => {
    if (!user) return false
    const siteRole = (user.role || '').toLowerCase()
    if (siteRole === 'admin' || siteRole === 'moderator') return true
    return membershipRole === 'owner' || membershipRole === 'moderator'
  }, [membershipRole, user])

  if (loading && !group && !error) {
    return <div className="text-center py-5">Loading group feed…</div>
  }

  if (error) {
    return <div className="alert alert-danger">{error}</div>
  }

  const privacy = normalizePrivacy(group?.privacy_state || group?.privacyState)
  const showPrivacyNotice = privacy !== 'public'

  return (
    <div className="group-feed" data-testid="group-feed">
      <GroupHeader group={group} membershipRole={membershipRole} canManage={canManage} />
      {showPrivacyNotice && (
        <div className="alert alert-info" data-testid="group-privacy-notice">
          {privacy === 'private'
            ? 'This is a private group. Only members can see the posts shared here.'
            : 'This group is unlisted. Only people with a direct link can find it.'}
        </div>
      )}
      {snippets.length === 0 ? (
        <div className="text-center py-5 text-muted" data-testid="group-empty">
          No snippets have been shared in this group yet.
        </div>
      ) : (
        <div data-testid="group-snippet-list">
          {snippets.map((snippet) => (
            <SnippetCard key={snippet.id} snippet={snippet} />
          ))}
        </div>
      )}
      {meta.nextPage && (
        <div className="text-center mt-3">
          <button className="btn btn-outline-primary" type="button" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}