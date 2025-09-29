import React, { useEffect, useState } from 'react'

export default function SearchBar({ value, onSearch, placeholder = 'Search…', debounce = 300, inputRef }) {
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
    <div className="search-bar" role="search">
      <span className="search-bar__icon" aria-hidden="true">
        🔍
      </span>
      <input
        type="search"
        className="search-bar__input"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={placeholder}
        aria-label="Search snippets"
        ref={inputRef}
      />
      {term ? (
        <button
          type="button"
          className="search-bar__clear"
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