import React, { useEffect, useMemo, useState, useId } from 'react'
import { createSnippet, listTags } from '../api'
import { capture } from '../lib/analytics'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import TagSelector from '../components/TagSelector'
import GroupSelector from '../components/GroupSelector'
import useBookSuggestions from '../hooks/useBookSuggestions'

export default function NewSnippet() {
  const nav = useNavigate()
  const { user } = useAuth()
  const [form, setForm] = useState({
    date_read: '',
    book_name: '',
    book_author: '',
    page_number: '',
    chapter: '',
    verse: '',
    text_snippet: '',
    thoughts: '',
    visibility: 'public'
  })

  const [msg, setMsg] = useState('')
  const [tags, setTags] = useState([])
  const [availableTags, setAvailableTags] = useState([])
  const [loadingTags, setLoadingTags] = useState(true)
  const [groupId, setGroupId] = useState(null)
  const bookInputId = useId()
  const bookListId = `${bookInputId}-options`

  const {
    options: fetchedBookOptions,
    loading: loadingBookSuggestions,
    error: bookSuggestionsError,
    retry: retryBookSuggestions
  } = useBookSuggestions(form.book_name)

  const bookOptions = useMemo(() => {
    const trimmed = (form.book_name || '').trim()
    if (!trimmed) return fetchedBookOptions
    const normalized = trimmed.toLowerCase()
    const exists = fetchedBookOptions.some((option) => option.value.toLowerCase() === normalized)
    if (exists) {
      return fetchedBookOptions
    }
    return [
      ...fetchedBookOptions,
      { value: trimmed, label: trimmed, author: null, source: 'input', isbn: null, googleVolumeId: null }
    ]
  }, [fetchedBookOptions, form.book_name])

  const bookOptionLookup = useMemo(() => {
    const map = new Map()
    bookOptions.forEach((option) => {
      const key = option.value.toLowerCase()
      if (!map.has(key)) {
        map.set(key, option)
      }
    })
    return map
  }, [bookOptions])

  const onChange = (e) => {
    const { name, value } = e.target
    const normalized = value.trim().toLowerCase()
    setForm((f) => {
      const next = { ...f, [name]: value }
      if (name === 'book_name') {
        const suggestion = bookOptionLookup.get(normalized)
        const hasAuthor = (f.book_author || '').trim().length > 0
        if (suggestion?.author && !hasAuthor) {
          next.book_author = suggestion.author
        }
      }
      return next
    })
    if (name === 'visibility' && value === 'private') {
      setGroupId(null)
    }
  }

  useEffect(() => {
    let ignore = false
    ;(async () => {
      try {
        const data = await listTags({ limit: 200 })
        if (!ignore) setAvailableTags(data)
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load tag suggestions', err)
        }
      } finally {
        if (!ignore) setLoadingTags(false)
      }
    })()
    return () => { ignore = true }
  }, [])

  const onSubmit = async (e) => {
    e.preventDefault()
    const payload = {
      date_read: form.date_read || null,
      book_name: form.book_name || null,
      book_author: form.book_author || null,
      page_number: form.page_number === '' ? null : Number(form.page_number),
      chapter: form.chapter || null,
      verse: form.verse || null,
      text_snippet: form.text_snippet || null,
      thoughts: form.thoughts || null,
      tags,
      visibility: form.visibility || 'public',
      group_id: form.visibility === 'private' || groupId == null ? null : groupId,
    }
    try {
      await createSnippet(payload)
      capture({
        event: 'snippet_created',
        props: {
          length: payload.text_snippet?.length || 0,
          has_thoughts: Boolean(payload.thoughts),
          book_id: payload.book_name,
          tags_count: payload.tags?.length || 0,
          source: 'web'
        }
      })
      nav('/')
    } catch (e) {
      setMsg('Failed to save snippet.')
    }
  }

  return (
    <div className="form-card">
      <div className="form-card__header">
        <h1 className="form-card__title">New snippet</h1>
        <p className="text-muted mb-0">
          Capture the highlight, share your reflection, and choose tags so the community can discover it.
        </p>
      </div>
      {msg && <div className="alert alert-danger">{msg}</div>}
      <form onSubmit={onSubmit} className="d-flex flex-column gap-4">
        <div className="row g-3">
          <div className="col-12">
            <label className="form-label">Book name</label>
            <input
              name="book_name"
              className="form-control"
              value={form.book_name}
              onChange={onChange}
              list={bookListId}
              autoComplete="off"
              placeholder="Search existing titles or add a new one"
            />
            <datalist id={bookListId}>
              {bookOptions.map((option, index) => (
                <option
                  key={`${option.source}:${option.value.toLowerCase()}:${index}`}
                  value={option.value}
                  label={option.label !== option.value ? option.label : undefined}
                />
              ))}
            </datalist>
            <div className="form-text">
              {loadingBookSuggestions
                ? 'Searching books…'
                : bookSuggestionsError || 'Start typing to search our catalog or Google Books.'}
            </div>
            {bookSuggestionsError ? (
              <button type="button" className="btn btn-link btn-sm p-0 mt-1" onClick={retryBookSuggestions}>
                Retry search
              </button>
            ) : null}
          </div>
          <div className="col-md-6">
            <label className="form-label">Author</label>
            <input
              name="book_author"
              className="form-control"
              value={form.book_author}
              onChange={onChange}
              autoComplete="off"
              placeholder="Who wrote this work?"
            />
            <div className="form-text">Capture who wrote the work you are quoting.</div>
          </div>
          <div className="col-md-6">
            <label className="form-label">Visibility</label>
            <select
              name="visibility"
              className="form-select"
              value={form.visibility}
              onChange={onChange}
            >
              <option value="public">Public (visible to the community)</option>
              <option value="private">Private (only you can view)</option>
            </select>
            <div className="form-text">Private snippets stay off group feeds and discovery pages.</div>
          </div>
          <div className="col-md-6">
            <GroupSelector
              value={form.visibility === 'private' ? null : groupId}
              onChange={setGroupId}
              disabled={form.visibility === 'private'}
              helperText="Group members will be able to view and discuss the snippet."
            />
          </div>
          <div className="col-md-3">
            <label className="form-label">Page number</label>
            <input name="page_number" className="form-control" value={form.page_number} onChange={onChange} />
          </div>
          <div className="col-md-3">
            <label className="form-label">Chapter</label>
            <input name="chapter" className="form-control" value={form.chapter} onChange={onChange} />
          </div>
          <div className="col-md-3">
            <label className="form-label">Verse</label>
            <input name="verse" className="form-control" value={form.verse} onChange={onChange} />
          </div>
          <div className="col-12">
            <label className="form-label">Text snippet</label>
            <textarea name="text_snippet" rows="5" className="form-control" value={form.text_snippet} onChange={onChange} />
          </div>
          <div className="col-12">
            <label className="form-label">Thoughts</label>
            <textarea name="thoughts" rows="4" className="form-control" value={form.thoughts} onChange={onChange} />
          </div>
          <div className="col-12">
            <label className="form-label">Tags</label>
            <TagSelector
              availableTags={availableTags}
              value={tags}
              onChange={setTags}
              allowCustom
              placeholder="Add a tag and press Add"
              showCounts
            />
            <div className="form-text">
              {loadingTags
                ? 'Loading tag suggestions…'
                : 'Select existing tags or add your own to help readers find this snippet.'}
            </div>
          </div>
        </div>
        <div className="d-flex justify-content-end">
          <button className="btn btn-primary" type="submit">
            Submit
          </button>
        </div>
      </form>
    </div>
  )
}
