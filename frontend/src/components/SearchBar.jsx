import React, { useEffect, useState } from 'react'

export default function SearchBar({ value, onSearch, placeholder = 'Search…', debounce = 300 }) {
  const [term, setTerm] = useState(value || '')

  useEffect(() => {
    setTerm(value || '')
  }, [value])

  useEffect(() => {
    if (!onSearch) return undefined
    const handle = setTimeout(() => {
      onSearch(term.trim())
    }, debounce)
    return () => clearTimeout(handle)
  }, [term, onSearch, debounce])

  return (
    <div className="input-group">
      <span className="input-group-text" aria-hidden="true">
        🔍
      </span>
      <input
        type="search"
        className="form-control"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={placeholder}
        aria-label="Search snippets"
      />
      {term ? (
        <button
          type="button"
          className="btn btn-outline-secondary"
          onClick={() => {
            setTerm('')
            if (onSearch) onSearch('')
          }}
        >
          Clear
        </button>
      ) : null}
    </div>
  )
}