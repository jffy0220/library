import React, { useState } from 'react'
import { createSnippet } from '../api'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

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
  })

  const [msg, setMsg] = useState('')

  const onChange = (e) => {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    const payload = {
      ...form,
      page_number: form.page_number === '' ? null : Number(form.page_number),
      date_read: form.date_read || null,
      text_snippet: form.text_snippet || null,
      thoughts: form.thoughts || null,
      created_by: user?.username || null,
    }
    try {
      await createSnippet(payload)
      nav('/')
    } catch (e) {
      setMsg('Failed to save snippet.')
    }
  }

  return (
    <div className="card shadow-sm">
      <div className="card-header">New snippet</div>
      <div className="card-body">
        {msg && <div className="alert alert-danger">{msg}</div>}
        <form onSubmit={onSubmit}>
          <div className="row g-3">
            <div className="col-md-4">
              <label className="form-label">Date read (YYYY-MM-DD)</label>
              <input name="date_read" className="form-control" value={form.date_read} onChange={onChange}/>
            </div>
            <div className="col-md-8">
              <label className="form-label">Book name</label>
              <input name="book_name" className="form-control" value={form.book_name} onChange={onChange}/>
            </div>
            <div className="col-md-6">
              <label className="form-label">User</label>
              <input className="form-control" value={user?.username || ''} readOnly />
              <div className="form-text">Signed in user</div>
            </div>
            <div className="col-md-3">
              <label className="form-label">Page number</label>
              <input name="page_number" className="form-control" value={form.page_number} onChange={onChange}/>
            </div>
            <div className="col-md-3">
              <label className="form-label">Chapter</label>
              <input name="chapter" className="form-control" value={form.chapter} onChange={onChange}/>
            </div>
            <div className="col-md-3">
              <label className="form-label">Verse</label>
              <input name="verse" className="form-control" value={form.verse} onChange={onChange}/>
            </div>
            <div className="col-12">
              <label className="form-label">Text snippet</label>
              <textarea name="text_snippet" rows="5" className="form-control" value={form.text_snippet} onChange={onChange}/>
            </div>
            <div className="col-12">
              <label className="form-label">Thoughts</label>
              <textarea name="thoughts" rows="4" className="form-control" value={form.thoughts} onChange={onChange}/>
            </div>
          </div>
          <div className="mt-3">
            <button className="btn btn-primary" type="submit">Submit</button>
          </div>
        </form>
      </div>
    </div>
  )
}
