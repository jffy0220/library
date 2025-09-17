import React from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Navbar from './components/Navbar'
import List from './pages/List'
import NewSnippet from './pages/NewSnippet'
import ViewSnippet from './pages/ViewSnippet'
import Login from './pages/Login'
import ModerationDashboard from './pages/ModerationDashboard'
import { AuthProvider, useAuth } from './auth'

function RequireAuth() {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="container mt-5">Loading…</div>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

function RequireModerator() {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="container mt-5">Loading…</div>
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
    return <div className="container mt-5">Loading…</div>
  }
  if (user) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}

function AuthenticatedLayout() {
  return (
    <>
      <Navbar />
      <div className="container">
        <Outlet />
      </div>
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<RequireAuth />}>
          <Route element={<AuthenticatedLayout />}>
            <Route path="/" element={<List />} />
            <Route path="/new" element={<NewSnippet />} />
            <Route path="/snippet/:id" element={<ViewSnippet />} />
            <Route element={<RequireModerator />}>
              <Route path="/moderation" element={<ModerationDashboard />} />
            </Route>
          </Route>
        </Route>
        <Route element={<RequireNoAuth />}>
          <Route path="/login" element={<Login />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
