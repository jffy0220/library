import React, { useState, useEffect } from 'react'
import { createSnippet, listTags } from '../api'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import TagSelector from '../components/TagSelector'
import GroupSelector from '../components/GroupSelector'

export default function NewSnippet() {
  const nav = useNavigate()
  const { user } = useAuth()
  const [form, setForm] = useState({
    date_read: '',
    book_name: '',
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

  const onChange = (e) => {
    const { name, value } = e.target
    setForm((f) => ({ ...f, [name]: value }))
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
          <div className="col-md-4">
            <label className="form-label">Date read (YYYY-MM-DD)</label>
            <input name="date_read" className="form-control" value={form.date_read} onChange={onChange} />
          </div>
          <div className="col-md-8">
            <label className="form-label">Book name</label>
            <input name="book_name" className="form-control" value={form.book_name} onChange={onChange} />
          </div>
          <div className="col-md-6">
            <label className="form-label">User</label>
            <input className="form-control" value={user?.username || ''} readOnly />
            <div className="form-text">Signed in user</div>
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
