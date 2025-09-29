import React from 'react'
import { Link } from 'react-router-dom'

export default function CapturePrompt({ onDismiss }) {
  return (
    <div className="engagement-prompt alert alert-info d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-3" role="status">
      <div>
        <strong>Add one insight today?</strong>
        <div className="text-body-secondary">Keep your streak going with a quick capture.</div>
      </div>
      <div className="d-flex gap-2">
        <Link className="btn btn-primary" to="/new">
          Add snippet
        </Link>
        <button type="button" className="btn btn-outline-secondary" onClick={onDismiss}>
          Not now
        </button>
      </div>
    </div>
  )
}