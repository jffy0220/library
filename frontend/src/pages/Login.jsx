import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Login() {
  const navigate = useNavigate()
  const { login, user, loading } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!loading && user) {
      navigate('/', { replace: true })
    }
  }, [loading, user, navigate])

  if (loading) {
    return <div className="container mt-5">Loading…</div>
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch (err) {
      const message = err?.response?.data?.detail || 'Login failed. Please check your credentials.'
      setError(message)
      setSubmitting(false)
    }
  }

  return (
    <div className="container mt-5">
      <div className="row justify-content-center">
        <div className="col-md-5 col-lg-4">
          <div className="card shadow-sm">
            <div className="card-body">
              <h5 className="card-title text-center mb-4">Sign in</h5>
              {error && <div className="alert alert-danger" role="alert">{error}</div>}
              <form onSubmit={onSubmit}>
                <div className="mb-3">
                  <label className="form-label" htmlFor="username">Username or email</label>
                  <input
                    id="username"
                    className="form-control"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    required
                  />
                </div>
                <div className="mb-3">
                  <label className="form-label" htmlFor="password">Password</label>
                  <input
                    id="password"
                    type="password"
                    className="form-control"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                  />
                </div>
                <button className="btn btn-primary w-100" type="submit" disabled={submitting}>
                  {submitting ? 'Signing in…' : 'Sign in'}
                </button>
              </form>
              <div className="mt-3 text-center">
                <p className="mb-1">
                  Need an account? <Link to="/register">Create one</Link>.
                </p>
                <p className="mb-0">
                  Forgot password? <Link to="/forgot-password">Reset it</Link>.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}