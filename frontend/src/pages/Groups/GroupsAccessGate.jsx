import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth'
import { getSubscriptionTier } from '../../features'

export default function GroupsAccessGate() {
  const { user } = useAuth()
  const tier = getSubscriptionTier(user)

  return (
    <div className="card shadow-sm" data-testid="groups-access-gate">
      <div className="card-header bg-warning-subtle">Groups require an upgrade</div>
      <div className="card-body">
        <p className="mb-3">
          Private and collaborative groups are available for premium library members.{' '}
          {tier === 'free'
            ? 'Upgrade to Plus or Pro to unlock shared feeds and invitations.'
            : `Your current plan (${tier}) does not include group collaboration.`}
        </p>
        <p className="mb-4">
          Ready to unlock group feeds, private discussions, and invite-only circles?
        </p>
        <Link className="btn btn-primary" to="/account/upgrade">
          View membership plans
        </Link>
      </div>
    </div>
  )
}