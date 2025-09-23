import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { acceptGroupInvite } from '../../api'

export default function GroupInviteAccept() {
  const { inviteCode } = useParams()
  const [status, setStatus] = useState('idle')
  const [message, setMessage] = useState(null)

  const handleAccept = async () => {
    if (!inviteCode || status === 'loading') return
    setStatus('loading')
    setMessage(null)
    try {
      await acceptGroupInvite(inviteCode)
      setStatus('success')
      setMessage('Invite accepted! You now have access to the group feed.')
    } catch (err) {
      console.error('Failed to accept invite', err)
      const detail = err?.response?.data?.detail
      setStatus('error')
      setMessage(detail || 'Unable to accept invite. It may have expired or been revoked.')
    }
  }

  return (
    <div className="card shadow-sm" data-testid="invite-accept">
      <div className="card-header">Accept group invite</div>
      <div className="card-body">
        <p className="mb-3">
          Use the button below to accept your invitation. Once accepted, the group will appear in your navigation and you can
          start sharing snippets with fellow members.
        </p>
        {message && (
          <div className={`alert alert-${status === 'success' ? 'success' : status === 'error' ? 'danger' : 'info'}`}>
            {message}
          </div>
        )}
        <div className="d-flex gap-2">
          <button className="btn btn-primary" type="button" onClick={handleAccept} disabled={status === 'loading'}>
            {status === 'loading' ? 'Accepting…' : 'Accept invite'}
          </button>
          {status === 'success' && (
            <Link className="btn btn-outline-secondary" to="/groups">
              View my groups
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}