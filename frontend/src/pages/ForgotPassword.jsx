import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { requestPasswordReset } from '../api'

export default function ForgotPassword() {
  const [identifier, setIdentifier] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const response = await requestPasswordReset({ identifier: identifier.trim() })
      setSuccess({
        message: response?.message || 'If an account exists, a reset email has been sent.',
        expiresAt: response?.expires_at || null
      })
    } catch (err) {
      const detail = err?.response?.data?.detail
      let message = 'Unable to process the request right now. Please try again later.'
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

  const expiresLabel = success?.expiresAt
    ? new Date(success.expiresAt).toLocaleString()
    : null

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">Reset your password</h1>
        <p className="auth-card__subtitle">
          Enter the email address or username linked to your account and we'll send instructions to reset your password.
        </p>
        {error && (
          <div className="alert alert-danger" role="alert">
            {error}
          </div>
        )}
        {success && (
          <div className="alert alert-success" role="alert">
            <p className="mb-0">{success.message}</p>
            {expiresLabel && <small className="d-block text-muted">Reset link expires on {expiresLabel}.</small>}
          </div>
        )}
        <form onSubmit={onSubmit} noValidate className="d-flex flex-column gap-3">
          <div>
            <label className="form-label" htmlFor="identifier">
              Email or username
            </label>
            <input
              id="identifier"
              className="form-control"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="email"
              required
              disabled={submitting}
            />
          </div>
          <button className="btn btn-primary w-100" type="submit" disabled={submitting}>
            {submitting ? 'Sending instructions…' : 'Send reset link'}
          </button>
        </form>
        <div className="auth-card__footer">
          <p className="mb-1">Remembered it? <Link to="/login">Return to sign in</Link>.</p>
          <p className="mb-0">Need an account? <Link to="/register">Create one</Link>.</p>
        </div>
      </div>
    </div>
  )
}