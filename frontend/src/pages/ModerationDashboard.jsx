import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listModerationReports, resolveModerationReport } from '../api'

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export default function ModerationDashboard() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [resolutions, setResolutions] = useState({})
  const [resolving, setResolving] = useState({})

  const fetchReports = useCallback(async (showSpinner = true) => {
    if (showSpinner) {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    setError(null)
    try {
      const data = await listModerationReports()
      setReports(data)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'Failed to load moderation reports.')
    } finally {
      if (showSpinner) {
        setLoading(false)
      } else {
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    fetchReports(true)
  }, [fetchReports])

  const onChangeNote = (reportId, value) => {
    setResolutions((prev) => ({ ...prev, [reportId]: value }))
  }

  const handleResolve = async (reportId) => {
    setError(null)
    setResolving((prev) => ({ ...prev, [reportId]: true }))
    try {
      const note = (resolutions[reportId] || '').trim()
      const updated = await resolveModerationReport(reportId, { resolution_note: note || null })
      setReports((prev) => prev.map((item) => (item.id === reportId ? updated : item)))
      setResolutions((prev) => {
        const next = { ...prev }
        delete next[reportId]
        return next
      })
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'Failed to resolve report.')
    } finally {
      setResolving((prev) => {
        const next = { ...prev }
        delete next[reportId]
        return next
      })
    }
  }

  const handleRefresh = () => {
    fetchReports(false)
  }

  const renderContentPreview = (report) => {
    if (report.content_type === 'snippet') {
      if (!report.snippet) {
        return <div className="text-muted fst-italic mt-2">Snippet is no longer available.</div>
      }
      return (
        <div className="mt-2">
          <div>
            <Link to={`/snippet/${report.snippet.id}`}>View snippet #{report.snippet.id}</Link>
          </div>
          <div className="small text-muted">
            {(report.snippet.book_name || 'Untitled')}
            {report.snippet.created_by_username && (
              <> · by {report.snippet.created_by_username}</>
            )}
          </div>
          {report.snippet.text_snippet && (
            <div className="mt-1 small text-muted">
              “{report.snippet.text_snippet.slice(0, 180)}{report.snippet.text_snippet.length > 180 ? '…' : ''}”
            </div>
          )}
        </div>
      )
    }

    if (!report.comment) {
      return <div className="text-muted fst-italic mt-2">Comment is no longer available.</div>
    }

    return (
      <div className="mt-2">
        <div>
          <Link to={`/snippet/${report.comment.snippet_id}`}>View snippet #{report.comment.snippet_id}</Link>
        </div>
        <div className="small text-muted">Comment by {report.comment.username}</div>
        <div className="mt-2 border rounded bg-light p-2" style={{ whiteSpace: 'pre-wrap' }}>
          {report.comment.content}
        </div>
      </div>
    )
  }

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>Moderation queue</span>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          onClick={handleRefresh}
          disabled={loading || refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      <div className="card-body">
        {error && <div className="alert alert-danger">{error}</div>}
        {loading ? (
          <div>Loading reports…</div>
        ) : reports.length === 0 ? (
          <div className="text-muted">No reports at the moment. Enjoy the calm!</div>
        ) : (
          <div className="d-flex flex-column gap-3">
            {reports.map((report) => {
              const isOpen = report.status === 'open'
              const noteValue = resolutions[report.id] || ''
              const isResolving = !!resolving[report.id]
              return (
                <div key={report.id} className="border rounded p-3">
                  <div className="d-flex justify-content-between align-items-start">
                    <div>
                      <h6 className="mb-1">
                        Report #{report.id} · {report.content_type === 'snippet' ? 'Snippet' : 'Comment'}
                      </h6>
                      <div className="small text-muted">
                        Reported by {report.reporter_username || 'Unknown user'} on {formatDate(report.created_utc)}
                      </div>
                    </div>
                    <span className={`badge ${isOpen ? 'bg-danger' : 'bg-success'}`}>
                      {report.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-2">
                    <strong>Reason:</strong>{' '}
                    {report.reason ? report.reason : <span className="text-muted">No reason provided.</span>}
                  </div>
                  {renderContentPreview(report)}
                  {isOpen ? (
                    <div className="mt-3">
                      <label className="form-label" htmlFor={`resolution-${report.id}`}>
                        Resolution note (optional)
                      </label>
                      <textarea
                        id={`resolution-${report.id}`}
                        className="form-control"
                        rows="2"
                        value={noteValue}
                        onChange={(event) => onChangeNote(report.id, event.target.value)}
                        disabled={isResolving}
                      />
                      <div className="mt-2">
                        <button
                          type="button"
                          className="btn btn-sm btn-success"
                          onClick={() => handleResolve(report.id)}
                          disabled={isResolving}
                        >
                          {isResolving ? 'Resolving…' : 'Resolve report'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 small text-muted">
                      Resolved by {report.resolved_by_username || 'Unknown user'} on {formatDate(report.resolved_utc)}.
                      {report.resolution_note && (
                        <div className="mt-1">Notes: {report.resolution_note}</div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}