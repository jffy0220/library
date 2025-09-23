import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createGroupInvite,
  getGroup,
  getGroupBySlug,
  listGroupInvites,
  listGroupMembers,
  removeGroupMember,
  updateGroupMember,
} from '../../api'

const ROLE_OPTIONS = [
  { value: 'member', label: 'Member' },
  { value: 'moderator', label: 'Moderator' },
  { value: 'owner', label: 'Owner' },
]

const normalizeRole = (value) => {
  if (!value) return ''
  return String(value).trim().toLowerCase()
}

const formatInviteStatus = (status) => {
  if (!status) return 'pending'
  const normalized = String(status).trim().toLowerCase()
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

const resolveGroupDetail = async (identifier) => {
  if (!identifier) throw new Error('Missing group identifier')
  const slugText = String(identifier)
  const numericId = Number.parseInt(slugText, 10)
  if (!Number.isNaN(numericId)) {
    try {
      const byId = await getGroup(numericId)
      if (byId) return byId
    } catch (err) {
      if (err?.response?.status !== 404) throw err
    }
  }
  try {
    return await getGroupBySlug(slugText)
  } catch (err) {
    if (!Number.isNaN(numericId) && err?.response?.status === 404) {
      return getGroup(numericId)
    }
    throw err
  }
}

function MemberRow({ member, onChangeRole, onRemove, saving, removing }) {
  const normalizedRole = normalizeRole(member.role)
  return (
    <tr data-testid="group-member-row">
      <td>{member.username || member.user_name || 'Unknown user'}</td>
      <td>
        <select
          className="form-select form-select-sm"
          value={normalizedRole}
          onChange={(event) => onChangeRole(member.user_id || member.userId, event.target.value)}
          disabled={saving || removing}
        >
          {ROLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </td>
      <td className="text-end">
        <button
          className="btn btn-sm btn-outline-danger"
          type="button"
          onClick={() => onRemove(member.user_id || member.userId)}
          disabled={removing || saving}
        >
          Remove
        </button>
      </td>
    </tr>
  )
}

function InviteRow({ invite }) {
  return (
    <tr data-testid="group-invite-row">
      <td>{invite.invited_user_email || invite.invitedUserEmail || 'Pending claim'}</td>
      <td>{formatInviteStatus(invite.status)}</td>
      <td>{invite.invite_code || invite.inviteCode}</td>
    </tr>
  )
}

export default function GroupManage() {
  const { groupSlug } = useParams()
  const [group, setGroup] = useState(null)
  const [members, setMembers] = useState([])
  const [invites, setInvites] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [memberError, setMemberError] = useState(null)
  const [inviteError, setInviteError] = useState(null)
  const [savingMemberId, setSavingMemberId] = useState(null)
  const [removingMemberId, setRemovingMemberId] = useState(null)
  const [inviteSubmitting, setInviteSubmitting] = useState(false)
  const [inviteSuccess, setInviteSuccess] = useState(null)
  const [inviteForm, setInviteForm] = useState({ email: '', expiresInHours: 168 })

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const detail = await resolveGroupDetail(groupSlug)
      setGroup(detail)
      const [memberList, inviteList] = await Promise.all([
        listGroupMembers(detail.id),
        listGroupInvites(detail.id, { status: 'pending' }),
      ])
      setMembers(Array.isArray(memberList) ? memberList : [])
      setInvites(Array.isArray(inviteList) ? inviteList : [])
    } catch (err) {
      console.error('Failed to load group management data', err)
      const status = err?.response?.status
      if (status === 403) {
        setError('You are not authorized to manage this group.')
      } else if (status === 404) {
        setError('Group not found.')
      } else {
        const detail = err?.response?.data?.detail
        setError(detail || 'Unable to load group management data.')
      }
      setGroup(null)
      setMembers([])
      setInvites([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupSlug])

  const handleChangeRole = async (userId, nextRole) => {
    if (!group || !userId) return
    const normalized = normalizeRole(nextRole)
    setSavingMemberId(userId)
    setMemberError(null)
    try {
      const updated = await updateGroupMember(group.id, userId, { role: normalized })
      setMembers((prev) => prev.map((member) => (member.user_id === userId || member.userId === userId ? updated : member)))
    } catch (err) {
      console.error('Failed to update membership', err)
      const detail = err?.response?.data?.detail
      setMemberError(detail || 'Unable to update member role.')
    } finally {
      setSavingMemberId(null)
    }
  }

  const handleRemoveMember = async (userId) => {
    if (!group || !userId) return
    if (!window.confirm('Remove this member from the group?')) {
      return
    }
    setRemovingMemberId(userId)
    setMemberError(null)
    try {
      await removeGroupMember(group.id, userId)
      setMembers((prev) => prev.filter((member) => (member.user_id || member.userId) !== userId))
    } catch (err) {
      console.error('Failed to remove member', err)
      const detail = err?.response?.data?.detail
      setMemberError(detail || 'Unable to remove member.')
    } finally {
      setRemovingMemberId(null)
    }
  }

  const handleInviteChange = (event) => {
    const { name, value } = event.target
    setInviteForm((prev) => ({ ...prev, [name]: value }))
  }

  const handleInviteSubmit = async (event) => {
    event.preventDefault()
    if (!group) return
    setInviteSubmitting(true)
    setInviteError(null)
    setInviteSuccess(null)
    try {
      const payload = {
        invitedUserEmail: inviteForm.email || undefined,
        expiresInHours: Number.parseInt(inviteForm.expiresInHours, 10) || undefined,
      }
      const invite = await createGroupInvite(group.id, payload)
      setInviteSuccess('Invite created successfully.')
      setInvites((prev) => [invite, ...prev])
      setInviteForm({ email: '', expiresInHours: inviteForm.expiresInHours })
    } catch (err) {
      console.error('Failed to create invite', err)
      const detail = err?.response?.data?.detail
      setInviteError(detail || 'Unable to create invite.')
    } finally {
      setInviteSubmitting(false)
    }
  }

  if (loading) {
    return <div className="text-center py-5">Loading group management…</div>
  }

  if (error) {
    return <div className="alert alert-danger">{error}</div>
  }

  return (
    <div className="group-manage" data-testid="group-manage">
      <div className="card shadow-sm mb-4">
        <div className="card-body">
          <h2 className="h4 mb-1">Manage members for {group?.name}</h2>
          <p className="text-muted mb-0">
            Update member roles or invite new collaborators into this group. Owners can manage other owners.
          </p>
        </div>
      </div>

      <div className="card shadow-sm mb-4">
        <div className="card-header">Current members</div>
        <div className="card-body">
          {memberError && <div className="alert alert-danger">{memberError}</div>}
          {members.length === 0 ? (
            <div className="text-muted" data-testid="no-members">
              No members have joined this group yet.
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table align-middle">
                <thead>
                  <tr>
                    <th scope="col">Member</th>
                    <th scope="col">Role</th>
                    <th scope="col" className="text-end">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((member) => (
                    <MemberRow
                      key={member.user_id || member.userId}
                      member={member}
                      onChangeRole={handleChangeRole}
                      onRemove={handleRemoveMember}
                      saving={savingMemberId === (member.user_id || member.userId)}
                      removing={removingMemberId === (member.user_id || member.userId)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="card shadow-sm">
        <div className="card-header">Pending invites</div>
        <div className="card-body">
          <p className="text-muted">
            Send an email invite or share a code. Invites expire automatically after the selected duration.
          </p>
          <form className="row g-3 mb-4" onSubmit={handleInviteSubmit}>
            <div className="col-md-6">
              <label className="form-label">Invitee email</label>
              <input
                className="form-control"
                name="email"
                type="email"
                placeholder="reader@example.com"
                value={inviteForm.email}
                onChange={handleInviteChange}
                required
              />
            </div>
            <div className="col-md-3">
              <label className="form-label">Expires in (hours)</label>
              <input
                className="form-control"
                name="expiresInHours"
                type="number"
                min="1"
                max="720"
                value={inviteForm.expiresInHours}
                onChange={handleInviteChange}
              />
            </div>
            <div className="col-md-3 d-flex align-items-end">
              <button className="btn btn-primary w-100" type="submit" disabled={inviteSubmitting}>
                {inviteSubmitting ? 'Creating…' : 'Send invite'}
              </button>
            </div>
          </form>
          {inviteError && <div className="alert alert-danger">{inviteError}</div>}
          {inviteSuccess && <div className="alert alert-success">{inviteSuccess}</div>}

          {invites.length === 0 ? (
            <div className="text-muted" data-testid="no-invites">
              No pending invites. Create one above to welcome a new member.
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table align-middle">
                <thead>
                  <tr>
                    <th scope="col">Email</th>
                    <th scope="col">Status</th>
                    <th scope="col">Invite code</th>
                  </tr>
                </thead>
                <tbody>
                  {invites.map((invite) => (
                    <InviteRow key={invite.id || invite.invite_code} invite={invite} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}