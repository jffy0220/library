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
    <div className="container mt-5">
      <div className="row justify-content-center">
        <div className="col-md-6 col-lg-5">
          <div className="card shadow-sm">
            <div className="card-body">
              <h5 className="card-title text-center mb-4">Reset your password</h5>
              <p className="text-muted small text-center">
                Enter the email address or username linked to your account and we'll send
                instructions to reset your password.
              </p>
              {error && (
                <div className="alert alert-danger" role="alert">
                  {error}
                </div>
              )}
              {success && (
                <div className="alert alert-success" role="alert">
                  <p className="mb-0">{success.message}</p>
                  {expiresLabel && (
                    <small className="d-block text-muted">
                      Reset link expires on {expiresLabel}.
                    </small>
                  )}
                </div>
              )}
              <form onSubmit={onSubmit} noValidate>
                <div className="mb-4">
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
              <div className="mt-3 text-center">
                <p className="mb-1">
                  Remembered it? <Link to="/login">Return to sign in</Link>.
                </p>
                <p className="mb-0">
                  Need an account? <Link to="/register">Create one</Link>.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}