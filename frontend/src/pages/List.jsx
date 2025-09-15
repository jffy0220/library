import React, { useEffect, useState } from 'react'
import { listSnippets } from '../api'
import { Link } from 'react-router-dom'

export default function List() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try { setRows(await listSnippets()) }
      finally { setLoading(false) }
    })()
  }, [])

  if (loading) return <div>Loading…</div>

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>Recent snippets</span>
      </div>
      <div className="list-group list-group-flush">
        {rows.length === 0 && <div className="list-group-item">No snippets yet.</div>}
        {rows.map(r => (
          <div key={r.id} className="list-group-item">
            <div className="d-flex w-100 justify-content-between">
              <h6 className="mb-1">
                <Link to={`/snippet/${r.id}`}>{r.book_name || 'Untitled'}</Link>
              </h6>
              <small className="text-muted">{new Date(r.created_utc).toLocaleString()}</small>
              <small className="text-muted">
                {r.created_by ? <>by {r.created_by} · </> : null}
                {r.page_number != null && <>p. {r.page_number}</>}
                {r.chapter && <>{r.page_number != null ? ' · ' : ''}ch. {r.chapter}</>}
                {r.verse && <>{(r.page_number != null || r.chapter) ? ' · ' : ''}v. {r.verse}</>}
              </small>
            </div>
            <small className="text-muted">
              {r.page_number != null && <>p. {r.page_number}</>}
              {r.chapter && <>{r.page_number != null ? ' · ' : ''}ch. {r.chapter}</>}
              {r.verse && <>{(r.page_number != null || r.chapter) ? ' · ' : ''}v. {r.verse}</>}
            </small>
            <div className="mt-1">{(r.text_snippet || '').slice(0, 200)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
