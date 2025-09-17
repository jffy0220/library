import React, { useMemo, useState } from 'react'

function normalizeTagName(name) {
  return (name || '').trim()
}

function tagsToSet(tags) {
  return new Set((tags || []).map((tag) => normalizeTagName(tag).toLowerCase()).filter(Boolean))
}

export default function TagSelector({
  availableTags = [],
  value = [],
  onChange,
  allowCustom = false,
  placeholder = 'Add a tag…',
  showCounts = false,
}) {
  const [draft, setDraft] = useState('')

  const normalizedSelected = useMemo(() => value.map(normalizeTagName).filter(Boolean), [value])
  const selectedLookup = useMemo(() => tagsToSet(normalizedSelected), [normalizedSelected])

  const emitChange = (nextTags) => {
    if (onChange) {
      const filtered = nextTags.map(normalizeTagName).filter(Boolean)
      onChange(filtered)
    }
  }

  const toggleTag = (tagName) => {
    const normalized = normalizeTagName(tagName)
    if (!normalized) return
    if (selectedLookup.has(normalized.toLowerCase())) {
      emitChange(normalizedSelected.filter((tag) => tag.toLowerCase() !== normalized.toLowerCase()))
    } else {
      emitChange([...normalizedSelected, normalized])
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    const normalized = normalizeTagName(draft)
    if (!normalized) return
    setDraft('')
    if (!selectedLookup.has(normalized.toLowerCase())) {
      emitChange([...normalizedSelected, normalized])
    }
  }

  const handleRemove = (tagName) => {
    emitChange(normalizedSelected.filter((tag) => tag.toLowerCase() !== tagName.toLowerCase()))
  }

  return (
    <div className="d-flex flex-column gap-2">
      {allowCustom && (
        <form onSubmit={handleSubmit} className="w-100">
          <div className="input-group">
            <span className="input-group-text">#</span>
            <input
              type="text"
              className="form-control"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={placeholder}
              aria-label="Add tag"
            />
            <button type="submit" className="btn btn-outline-secondary">
              Add
            </button>
          </div>
        </form>
      )}

      {normalizedSelected.length > 0 ? (
        <div className="d-flex flex-wrap gap-2">
          {normalizedSelected.map((tag) => (
            <span key={tag.toLowerCase()} className="badge bg-primary d-flex align-items-center gap-2">
              <span>#{tag}</span>
              <button
                type="button"
                className="btn-close btn-close-white btn-sm"
                aria-label={`Remove tag ${tag}`}
                onClick={() => handleRemove(tag)}
              />
            </span>
          ))}
        </div>
      ) : (
        <div className="text-muted small">No tags selected.</div>
      )}

      {availableTags.length > 0 ? (
        <div className="d-flex flex-wrap gap-2">
          {availableTags.map((tag) => {
            const name = normalizeTagName(tag.name)
            if (!name) return null
            const active = selectedLookup.has(name.toLowerCase())
            return (
              <button
                key={tag.slug || name}
                type="button"
                className={`btn btn-sm ${active ? 'btn-primary' : 'btn-outline-secondary'}`}
                onClick={() => toggleTag(name)}
              >
                #{name}
                {showCounts && typeof tag.usage_count === 'number' ? (
                  <span className="badge bg-light text-dark ms-1">{tag.usage_count}</span>
                ) : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}