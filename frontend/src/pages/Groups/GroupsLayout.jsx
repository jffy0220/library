import React from 'react'
import { Outlet } from 'react-router-dom'
import { useAuth } from '../../auth'
import { hasGroupAccess } from '../../features'
import GroupsAccessGate from './GroupsAccessGate'

export default function GroupsLayout() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="mt-5 text-center" data-testid="groups-loading">
        Loading group tools…
      </div>
    )
  }

  if (!hasGroupAccess(user)) {
    return <GroupsAccessGate />
  }

  return (
    <div className="groups-layout" data-testid="groups-layout">
      <Outlet />
    </div>
  )
}
