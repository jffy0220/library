import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { register as registerAccount } from '../api'
import { capture } from '../lib/analytics'

export default function Register() {
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: ''
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const onChange = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess(null)
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password
      }
      const response = await registerAccount(payload)
      setSuccess({
        message: response?.message || 'Registration successful.',
        expiresAt: response?.expires_at || null
      })
      capture({
        event: 'user_signed_up',
        props: {
          has_email: Boolean(payload.email)
        }
      })
    } catch (err) {
      const detail = err?.response?.data?.detail
      let message = 'Registration failed. Please try again.'
      if (Array.isArray(detail) && detail.length > 0) {
        message = detail[0]?.msg || message
      } else if (typeof detail === 'string') {
        message = detail
      }
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  const disabled = submitting || Boolean(success)

  const expiresLabel = success?.expiresAt
    ? new Date(success.expiresAt).toLocaleString()
    : null

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">Create your account</h1>
        <p className="auth-card__subtitle">Join fellow readers, highlight your favorite lines, and follow new discoveries.</p>
        {error && (
          <div className="alert alert-danger" role="alert">
            {error}
          </div>
        )}
        {success && (
          <div className="alert alert-success" role="alert">
            <p className="mb-0">{success.message}</p>
            {expiresLabel && (
              <small className="d-block text-muted">Token expires on {expiresLabel}.</small>
            )}
          </div>
        )}
        <form onSubmit={onSubmit} noValidate className="d-flex flex-column gap-3">
          <div>
            <label className="form-label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              name="username"
              className="form-control"
              value={form.username}
              onChange={onChange}
              autoComplete="username"
              maxLength={80}
              required
              disabled={disabled}
            />
          </div>
          <div>
            <label className="form-label" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              type="email"
              name="email"
              className="form-control"
              value={form.email}
              onChange={onChange}
              autoComplete="email"
              required
              disabled={disabled}
            />
          </div>
          <div>
            <label className="form-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              name="password"
              className="form-control"
              value={form.password}
              onChange={onChange}
              autoComplete="new-password"
              minLength={8}
              required
              disabled={disabled}
            />
            <small className="form-text text-muted">
              Use at least 8 characters for a strong password.
            </small>
          </div>
          <div>
            <label className="form-label" htmlFor="confirmPassword">
              Confirm password
            </label>
            <input
              id="confirmPassword"
              type="password"
              name="confirmPassword"
              className="form-control"
              value={form.confirmPassword}
              onChange={onChange}
              autoComplete="new-password"
              minLength={8}
              required
              disabled={disabled}
            />
          </div>
          <button className="btn btn-primary w-100" type="submit" disabled={disabled}>
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <div className="auth-card__footer">
          <p className="mb-1">Already have an account? <Link to="/login">Sign in</Link>.</p>
          <p className="mb-0">Forgot your password? <Link to="/forgot-password">Reset it</Link>.</p>
        </div>
      </div>
    </div>
  )
}