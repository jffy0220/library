import React, { useEffect, useMemo, useState } from 'react'
import { listMyGroupMemberships } from '../api'
import { useAuth } from '../auth'

const normalizePrivacy = (value) => {
  if (!value) return 'public'
  if (typeof value === 'string') return value.trim().toLowerCase()
  return 'public'
}

const normalizeMembershipRecord = (record) => {
  if (!record) return null
  const group = record.group || record
  const privacy = normalizePrivacy(group.privacy_state || group.privacyState)
  return {
    id: group.id,
    name: group.name,
    slug: group.slug,
    privacy,
    role: record.role || record.group_role || record.membershipRole || group.role || null,
  }
}

export default function GroupSelector({ value, onChange, disabled = false, helperText }) {
  const { user } = useAuth()
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError(null)
    if (!user) {
      setGroups([])
      setLoading(false)
      return () => {}
    }
    ;(async () => {
      try {
        const memberships = await listMyGroupMemberships()
        if (!ignore) {
          const normalized = Array.isArray(memberships)
            ? memberships
                .map(normalizeMembershipRecord)
                .filter(Boolean)
                .sort((a, b) => a.name.localeCompare(b.name))
            : []
          setGroups(normalized)
        }
      } catch (err) {
        if (!ignore) {
          if (err?.response?.status === 403) {
            console.error('Failed to load group memberships', err)
          }
          setError('Unable to load your group memeberships')
          setGroups([])
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [user?.id])

  const selectedGroup = useMemo(() => {
    if (value == null) return null
    const target = String(value)
    return groups.find((group) => String(group.id) === target || group.slug === target) || null
  }, [groups, value])

  const visibilityMessage = useMemo(() => {
    if (selectedGroup) {
      if (selectedGroup.privacy === 'unlisted') {
        return 'Unlisted groups stay off discovery pages. Only members can view the shared snippets.'
      }
      return 'Only members of this group will be able to view the snippet and its discussion.'
    }
    return 'Snippets without a group are visible to the entire community unless you mark them private.'
  }, [selectedGroup])

  const handleChange = (event) => {
    const nextValue = event.target.value
    if (!nextValue) {
      onChange?.(null)
      return
    }
    const parsed = Number.parseInt(nextValue, 10)
    if (Number.isNaN(parsed)) {
      onChange?.(nextValue)
    } else {
      onChange?.(parsed)
    }
  }

  return (
    <div className="group-selector" data-testid="group-selector">
      <div className="group-selector__header">
        <label className="form-label mb-0">Share with a group</label>
        {loading && <span className="text-muted small">Loading groups…</span>}
      </div>
      <select
        className="group-selector__select"
        value={value == null ? '' : String(value)}
        onChange={handleChange}
        disabled={disabled || loading || groups.length === 0}
      >
        <option value="">No group (public snippet)</option>
        {groups.map((group) => (
          <option key={group.id} value={group.id}>
            {group.name} {group.role ? `(${group.role})` : ''}
          </option>
        ))}
      </select>
      <div className="group-selector__message">
        {error ? (
          <span className="text-danger">{error}</span>
        ) : (
          <>
            {visibilityMessage}
            {helperText && (
              <>
                <br />
                {helperText}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}