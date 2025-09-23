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
    <div className="tag-selector">
      {allowCustom && (
        <form onSubmit={handleSubmit} className="tag-selector__form">
          <span aria-hidden="true">#</span>
          <input
            type="text"
            className="tag-selector__input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={placeholder}
            aria-label="Add tag"
          />
          <button type="submit" className="tag-selector__submit">
            Add
          </button>
        </form>
      )}

      {normalizedSelected.length > 0 ? (
        <div className="tag-selector__selected">
          {normalizedSelected.map((tag) => (
            <span key={tag.toLowerCase()} className="tag-chip tag-chip--active">
              <span>#{tag}</span>
              <button
                type="button"
                className="tag-chip__remove"
                aria-label={`Remove tag ${tag}`}
                onClick={() => handleRemove(tag)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : (
        <div className="text-muted small">No tags selected.</div>
      )}

      {availableTags.length > 0 ? (
        <div className="tag-selector__choices">
          {availableTags.map((tag) => {
            const name = normalizeTagName(tag.name)
            if (!name) return null
            const active = selectedLookup.has(name.toLowerCase())
            return (
              <button
                key={tag.slug || name}
                type="button"
                className={`tag-chip ${active ? 'tag-chip--active' : 'tag-chip--outlined'}`}
                onClick={() => toggleTag(name)}
              >
                #{name}
                {showCounts && typeof tag.usage_count === 'number' ? (
                  <span className="tag-chip__count">{tag.usage_count}</span>
                ) : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}