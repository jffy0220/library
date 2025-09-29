import React, { useId, useMemo, useState } from 'react'

function normalizeTagName(name) {
  return (name || '').trim()
}

export default function TagInput({
  availableTags = [],
  value = [],
  onChange,
  disabled = false,
  placeholder = 'Start typing to add a tag',
  inputId,
}) {
  const [draft, setDraft] = useState('')
  const datalistId = useId()

  const selectedTags = useMemo(
    () =>
      value
        .map(normalizeTagName)
        .filter(Boolean),
    [value]
  )

  const selectedLookup = useMemo(() => {
    const lookup = new Set()
    selectedTags.forEach((tag) => lookup.add(tag.toLowerCase()))
    return lookup
  }, [selectedTags])

  const suggestionNames = useMemo(() => {
    const seen = new Set()
    const names = []
    availableTags.forEach((tag) => {
      const raw = typeof tag === 'string' ? tag : tag?.name
      const normalized = normalizeTagName(raw)
      if (!normalized) return
      const key = normalized.toLowerCase()
      if (seen.has(key)) return
      seen.add(key)
      names.push(normalized)
    })
    names.sort((a, b) => a.localeCompare(b))
    return names
  }, [availableTags])

  const emitChange = (next) => {
    if (onChange) {
      const unique = []
      const seen = new Set()
      next.forEach((tag) => {
        const normalized = normalizeTagName(tag)
        if (!normalized) return
        const key = normalized.toLowerCase()
        if (seen.has(key)) return
        seen.add(key)
        unique.push(normalized)
      })
      onChange(unique)
    }
  }

  const addTag = (tagName) => {
    const normalized = normalizeTagName(tagName)
    if (!normalized) return
    if (selectedLookup.has(normalized.toLowerCase())) return
    emitChange([...selectedTags, normalized])
    setDraft('')
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    addTag(draft)
  }

  const handleRemove = (tagName) => {
    const filtered = selectedTags.filter((tag) => tag.toLowerCase() !== tagName.toLowerCase())
    emitChange(filtered)
  }

  const handleKeyDown = (event) => {
    if (disabled) return
    if (['Enter', 'Tab', ','].includes(event.key)) {
      const normalized = normalizeTagName(draft)
      if (normalized) {
        event.preventDefault()
        addTag(normalized)
        return
      }
    }
    if (event.key === 'Backspace' && !draft) {
      if (selectedTags.length === 0) return
      event.preventDefault()
      const last = selectedTags[selectedTags.length - 1]
      handleRemove(last)
    }
  }

  return (
    <div>
      {selectedTags.length > 0 ? (
        <div className="d-flex flex-wrap gap-2 mb-2">
          {selectedTags.map((tag) => (
            <span
              key={tag.toLowerCase()}
              className="badge rounded-pill bg-secondary d-inline-flex align-items-center gap-2 px-3 py-2"
            >
              <span>#{tag}</span>
              <button
                type="button"
                className="btn btn-sm btn-link text-decoration-none text-white p-0 ms-1"
                onClick={() => handleRemove(tag)}
                aria-label={`Remove tag ${tag}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="text-muted small mb-2">No tags yet.</p>
      )}

      <form className="input-group" onSubmit={handleSubmit}>
        <span className="input-group-text">#</span>
        <input
          id={inputId}
          className="form-control"
          type="text"
          list={datalistId}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
        />
        <button type="submit" className="btn btn-outline-secondary" disabled={disabled}>
          Add
        </button>
      </form>

      <datalist id={datalistId}>
        {suggestionNames.map((name) => (
          <option key={name.toLowerCase()} value={name} />
        ))}
      </datalist>
    </div>
  )
}