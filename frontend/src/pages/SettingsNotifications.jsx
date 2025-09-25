import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useNotificationPreferences } from '../hooks/useNotificationPreferences'

const DEFAULT_STATE = {
  replyToSnippet: true,
  replyToComment: true,
  mention: true,
  voteOnYourSnippet: true,
  moderationUpdate: true,
  system: true,
  emailDigest: 'weekly'
}

const EVENT_FIELDS = [
  {
    key: 'replyToSnippet',
    label: 'Replies to your snippets',
    description: 'Get alerted when someone comments on a snippet you shared.'
  },
  {
    key: 'replyToComment',
    label: 'Replies to your comments',
    description: 'Find out when the conversation continues on your comment.'
  },
  {
    key: 'mention',
    label: 'Mentions',
    description: 'Know when another reader tags you in a discussion.'
  },
  {
    key: 'voteOnYourSnippet',
    label: 'Votes on your snippets',
    description: 'Stay in the loop when readers react to your snippets.'
  },
  {
    key: 'moderationUpdate',
    label: 'Moderation updates',
    description: 'Follow the status of moderation reviews you are involved in.'
  },
  {
    key: 'system',
    label: 'Product updates',
    description: 'Occasional announcements about new features or policies.'
  }
]

const EMAIL_DIGEST_OPTIONS = [
  {
    value: 'off',
    label: 'Off',
    description: 'Do not send summary emails.'
  },
  {
    value: 'daily',
    label: 'Daily',
    description: 'Receive a once-a-day summary when you have unread activity.'
  },
  {
    value: 'weekly',
    label: 'Weekly',
    description: 'Get a weekly snapshot of anything you missed.'
  }
]

function normalizePreferences(preferences) {
  if (!preferences || typeof preferences !== 'object') {
    return { ...DEFAULT_STATE }
  }
  return {
    replyToSnippet:
      preferences.replyToSnippet ?? preferences.reply_to_snippet ?? DEFAULT_STATE.replyToSnippet,
    replyToComment:
      preferences.replyToComment ?? preferences.reply_to_comment ?? DEFAULT_STATE.replyToComment,
    mention: preferences.mention ?? DEFAULT_STATE.mention,
    voteOnYourSnippet:
      preferences.voteOnYourSnippet ??
      preferences.vote_on_your_snippet ??
      DEFAULT_STATE.voteOnYourSnippet,
    moderationUpdate:
      preferences.moderationUpdate ??
      preferences.moderation_update ??
      DEFAULT_STATE.moderationUpdate,
    system: preferences.system ?? DEFAULT_STATE.system,
    emailDigest: preferences.emailDigest ?? preferences.email_digest ?? DEFAULT_STATE.emailDigest
  }
}

export default function NotificationSettingsPage() {
  const {
    preferences,
    loading,
    error,
    updating,
    update,
    refresh
  } = useNotificationPreferences()
  const [formState, setFormState] = useState({ ...DEFAULT_STATE })
  const [status, setStatus] = useState('idle')
  const [statusMessage, setStatusMessage] = useState('')

  useEffect(() => {
    setFormState(normalizePreferences(preferences))
  }, [preferences])

  const dirty = useMemo(() => {
    const normalized = normalizePreferences(preferences)
    return EVENT_FIELDS.some((field) => formState[field.key] !== normalized[field.key]) ||
      formState.emailDigest !== normalized.emailDigest
  }, [formState, preferences])

  useEffect(() => {
    if (status === 'success' || status === 'error') {
      const timeout = setTimeout(() => {
        setStatus('idle')
        setStatusMessage('')
      }, 4000)
      return () => clearTimeout(timeout)
    }
    return undefined
  }, [status])

  const handleToggleChange = (key) => (event) => {
    setFormState((prev) => ({ ...prev, [key]: event.target.checked }))
  }

  const handleDigestChange = (event) => {
    setFormState((prev) => ({ ...prev, emailDigest: event.target.value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setStatus('saving')
    setStatusMessage('')
    try {
      await update({
        replyToSnippet: formState.replyToSnippet,
        replyToComment: formState.replyToComment,
        mention: formState.mention,
        voteOnYourSnippet: formState.voteOnYourSnippet,
        moderationUpdate: formState.moderationUpdate,
        system: formState.system,
        emailDigest: formState.emailDigest
      })
      setStatus('success')
      setStatusMessage('Your notification preferences were saved.')
    } catch (err) {
      console.error('Failed to update notification preferences', err)
      setStatus('error')
      setStatusMessage('We could not save your changes. Please try again.')
    }
  }

  const handleReset = async () => {
    setStatus('idle')
    setStatusMessage('')
    try {
      await refresh()
    } catch (err) {
      console.error('Failed to reload notification preferences', err)
    }
  }

  const disableActions = loading || updating

  return (
    <div className="container-md">
      <div className="d-flex align-items-center justify-content-between flex-wrap gap-3 mb-4">
        <div>
          <h1 className="h3 mb-1">Notification preferences</h1>
          <p className="text-body-secondary mb-0">
            Decide how Book Snippets keeps you up to date.
          </p>
        </div>
        <Link className="btn btn-outline-secondary" to="/notifications">
          Back to notifications
        </Link>
      </div>
      {error && (
        <div className="alert alert-danger" role="status">
          We were unable to load your preferences. Please refresh the page to try again.
        </div>
      )}
      {status === 'success' && statusMessage && (
        <div className="alert alert-success" role="status">
          {statusMessage}
        </div>
      )}
      {status === 'error' && statusMessage && (
        <div className="alert alert-danger" role="status">
          {statusMessage}
        </div>
      )}
      <form onSubmit={handleSubmit} className="card shadow-sm">
        <div className="card-body p-4">
          <section className="mb-4">
            <h2 className="h5">Real-time alerts</h2>
            <p className="text-body-secondary">
              Choose the activity that should trigger in-app notifications and toasts.
            </p>
            <div className="d-flex flex-column gap-3">
              {EVENT_FIELDS.map((field) => (
                <div className="form-check form-switch" key={field.key}>
                  <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id={`pref-${field.key}`}
                    checked={Boolean(formState[field.key])}
                    onChange={handleToggleChange(field.key)}
                    disabled={disableActions}
                  />
                  <label className="form-check-label fw-semibold" htmlFor={`pref-${field.key}`}>
                    {field.label}
                  </label>
                  <div className="form-text">{field.description}</div>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h2 className="h5">Email digests</h2>
            <p className="text-body-secondary">
              We bundle unread notifications into a digest so you can catch up later.
            </p>
            <div className="d-flex flex-column gap-2">
              {EMAIL_DIGEST_OPTIONS.map((option) => (
                <div className="form-check" key={option.value}>
                  <input
                    className="form-check-input"
                    type="radio"
                    name="emailDigest"
                    id={`digest-${option.value}`}
                    value={option.value}
                    checked={formState.emailDigest === option.value}
                    onChange={handleDigestChange}
                    disabled={disableActions}
                  />
                  <label className="form-check-label" htmlFor={`digest-${option.value}`}>
                    <span className="fw-semibold d-block">{option.label}</span>
                    <span className="text-body-secondary small">{option.description}</span>
                  </label>
                </div>
              ))}
            </div>
          </section>
        </div>
        <div className="card-footer d-flex justify-content-between align-items-center gap-3">
          <button
            type="button"
            className="btn btn-outline-secondary"
            onClick={handleReset}
            disabled={disableActions}
          >
            Reset
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={disableActions || !dirty}
          >
            {updating || status === 'saving' ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </form>
    </div>
  )
}