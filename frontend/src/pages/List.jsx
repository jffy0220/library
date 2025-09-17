import React, { useEffect, useState } from 'react'
import { listSnippets } from '../api'
import { Link } from 'react-router-dom'

export default function List() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let ignore = false
    ;(async () => {
      try {
        const data = await listSnippets()
        if (!ignore) setRows(data)
      } catch (err) {
        if (!ignore && err?.response?.status !== 401) {
          console.error('Failed to load snippets', err)
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    })()
    return () => { ignore = true }
  }, [])

  if (loading) return <div>Loading…</div>

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>Recent snippets</span>
      </div>
      <div className="list-group list-group-flush">
        {rows.length === 0 && <div className="list-group-item">No snippets yet.</div>}
        {rows.map((r) => {
          const meta = []
          if (r.created_by_username) meta.push(`by ${r.created_by_username}`)
          if (r.page_number != null) meta.push(`p. ${r.page_number}`)
          if (r.chapter) meta.push(`ch. ${r.chapter}`)
          if (r.verse) meta.push(`v. ${r.verse}`)
          return (
            <div key={r.id} className="list-group-item">
              <div className="d-flex w-100 justify-content-between align-items-baseline gap-2">
                <h6 className="mb-1 mb-sm-0">
                  <Link to={`/snippet/${r.id}`}>{r.book_name || 'Untitled'}</Link>
                </h6>
                <small className="text-muted">{new Date(r.created_utc).toLocaleString()}</small>
              </div>
              {meta.length > 0 && (
                <small className="text-muted d-block mt-1">{meta.join(' · ')}</small>
              )}
              <div className="mt-2">{(r.text_snippet || '').slice(0, 200)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
