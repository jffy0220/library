import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getSnippet } from '../api'

export default function ViewSnippet() {
  const { id } = useParams()
  const [row, setRow] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try { setRow(await getSnippet(id)) }
      finally { setLoading(false) }
    })()
  }, [id])

  if (loading) return <div>Loading…</div>
  if (!row) return <div>Not found.</div>

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>Snippet #{row.id}</span>
        <Link className="btn btn-sm btn-secondary" to="/">Back</Link>
      </div>
      <div className="card-body">
        <div className="row g-3">
          <div className="col-md-4">
            <label className="form-label">Date read</label>
            <input className="form-control" value={row.date_read || ''} readOnly />
          </div>
          <div className="col-md-8">
            <label className="form-label">Book name</label>
            <input className="form-control" value={row.book_name || ''} readOnly />
          </div>
          <div className="col-md-6">
            <label className="form-label">User</label>
            <input className="form-control" value={row.created_by || ''} readOnly />
        </div>
          <div className="col-md-3">
            <label className="form-label">Page number</label>
            <input className="form-control" value={row.page_number ?? ''} readOnly />
          </div>
          <div className="col-md-3">
            <label className="form-label">Chapter</label>
            <input className="form-control" value={row.chapter || ''} readOnly />
          </div>
          <div className="col-md-3">
            <label className="form-label">Verse</label>
            <input className="form-control" value={row.verse || ''} readOnly />
          </div>
          <div className="col-12">
            <label className="form-label">Text snippet</label>
            <textarea className="form-control" rows="8" value={row.text_snippet || ''} readOnly />
          </div>
          <div className="col-12">
            <label className="form-label">Thoughts</label>
            <textarea className="form-control" rows="6" value={row.thoughts || ''} readOnly />
          </div>
        </div>
      </div>
    </div>
  )
}
