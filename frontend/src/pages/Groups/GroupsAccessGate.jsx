import React from 'react'
import { Link } from 'react-router-dom'

export default function GroupsAccessGate() {
  return (
    <div className="card shadow-sm" data-testid="groups-access-gate">
      <div className="card-header bg-light">Sign in to explore groups</div>
      <div className="card-body">
        <p className="mb-3">Join the community to create and collaborate with reading groups.</p>
        <div className="d-flex flex-wrap gap-2">
          <Link className="btn btn-primary" to="/login">
            Sign in
          </Link>
          <Link className="btn btn-outline-secondary" to="/register">
            Create an account
          </Link>
        </div>
      </div>
    </div>
  )
}