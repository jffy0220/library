import React from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Navbar from './components/Navbar'
import List from './pages/List'
import NewSnippet from './pages/NewSnippet'
import ViewSnippet from './pages/ViewSnippet'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ModerationDashboard from './pages/ModerationDashboard'
import NotificationsPage from './pages/Notfications'
import GroupDiscover from './pages/Groups/GroupDiscover'
import GroupFeed from './pages/Groups/GroupFeed'
import GroupManager from './pages/Groups/GroupManager'
import GroupInviteAccept from './pages/Groups/GroupInviteAccept'
import GroupsLayout from './pages/Groups/GroupsLayout'
import { AuthProvider, useAuth } from './auth'

function RequireAuth() {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="callout">Loading…</div>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

function RequireModerator() {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="callout">Loading…</div>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (user.role !== 'moderator' && user.role !== 'admin') {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}

function RequireNoAuth() {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="callout">Loading…</div>
  }
  if (user) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}

function AppLayout() {
  return (
    <div className="app-shell">
      <Navbar />
      <main className="app-content">
        <div className="app-content__inner">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<AppLayout />}>
            <Route path="/" element={<List />} />
            <Route path="/snippet/:id" element={<ViewSnippet />} />
            <Route element={<RequireAuth />}>
              <Route path="/new" element={<NewSnippet />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/groups" element={<GroupsLayout />}>
                <Route index element={<GroupDiscover />} />
                <Route path="discover" element={<GroupDiscover />} />
                <Route path="invite/:inviteCode" element={<GroupInviteAccept />} />
                <Route path=":groupSlug" element={<GroupFeed />} />
                <Route path=":groupSlug/manage" element={<GroupManager />} />
              </Route>
            </Route>
            <Route element={<RequireModerator />}>
              <Route path="/moderation" element={<ModerationDashboard />} />
            </Route>
        </Route>
        <Route element={<RequireNoAuth />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
