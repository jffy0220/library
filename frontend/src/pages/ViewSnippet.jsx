import React, { useCallback, useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  getSnippet,
  listSnippetComments,
  createSnippetComment,
  voteComment,
  updateSnippet,
  deleteSnippet,
  updateComment,
  deleteComment,
  reportSnippet,
  reportComment,
  listTags,
  getGroup,
} from '../api'
import { useAuth } from '../auth'
import TagSelector from '../components/TagSelector'
import GroupSelector from '../components/GroupSelector'
import { capture } from '../lib/analytics'

const makeEmptySnippetForm = () => ({
  date_read: '',
  book_name: '',
  book_author: '',
  page_number: '',
  chapter: '',
  verse: '',
  text_snippet: '',
  thoughts: '',
  visibility: 'public',
})

export default function ViewSnippet() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [row, setRow] = useState(null)
  const [loading, setLoading] = useState(true)
  const [comments, setComments] = useState([])
  const [commentsLoading, setCommentsLoading] = useState(true)
  const [commentContent, setCommentContent] = useState('')
  const [commentError, setCommentError] = useState(null)
  const [submittingComment, setSubmittingComment] = useState(false)
  const [voting, setVoting] = useState({})
  const [snippetAlert, setSnippetAlert] = useState(null)
  const [commentAlert, setCommentAlert] = useState(null)
  const [commentToast, setCommentToast] = useState(null)

  const [editingSnippet, setEditingSnippet] = useState(false)
  const [snippetForm, setSnippetForm] = useState(makeEmptySnippetForm)
  const [snippetSaving, setSnippetSaving] = useState(false)
  const [deletingSnippet, setDeletingSnippet] = useState(false)
  const [snippetTags, setSnippetTags] = useState([])
  const [availableTags, setAvailableTags] = useState([])
  const [tagsLoading, setTagsLoading] = useState(true)
  const [snippetGroupId, setSnippetGroupId] = useState(null)
  const [groupDetail, setGroupDetail] = useState(null)

  const [showSnippetReport, setShowSnippetReport] = useState(false)
  const [snippetReportReason, setSnippetReportReason] = useState('')
  const [snippetReportSubmitting, setSnippetReportSubmitting] = useState(false)

  const [editingCommentId, setEditingCommentId] = useState(null)
  const [commentEditContent, setCommentEditContent] = useState('')
  const [commentEditError, setCommentEditError] = useState(null)
  const [commentSavingEdit, setCommentSavingEdit] = useState(false)
  const [deletingCommentId, setDeletingCommentId] = useState(null)

  const [reportingCommentId, setReportingCommentId] = useState(null)
  const [commentReportReason, setCommentReportReason] = useState('')
  const [commentReportSubmitting, setCommentReportSubmitting] = useState(false)

  const canModerate = user && (user.role === 'moderator' || user.role === 'admin')
  const snippetTextInputId = 'view-snippet-text'

  useEffect(() => {
    let ignore = false
    setSnippetAlert(null)
    ;(async () => {
      try {
        const data = await getSnippet(id)
        if (!ignore) setRow(data)
      } catch (err) {
        if (!ignore) {
          if (err?.response?.status === 404) {
            setRow(null)
          } else if (err?.response?.status !== 401) {
            console.error('Failed to load snippet', err)
          }
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [id])

  useEffect(() => {
    let ignore = false
    setComments([])
    setCommentsLoading(true)
    ;(async () => {
      try {
        const data = await listSnippetComments(id)
        if (!ignore) setComments(data)
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load comments', err)
        }
      } finally {
        if (!ignore) setCommentsLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [id])

  useEffect(() => {
    let ignore = false
    setTagsLoading(true)
    ;(async () => {
      try {
        const data = await listTags({ limit: 200 })
        if (!ignore) setAvailableTags(data)
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load tag suggestions', err)
        }
      } finally {
        if (!ignore) setTagsLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!commentToast) return undefined
    const timeout = setTimeout(() => setCommentToast(null), 4000)
    return () => clearTimeout(timeout)
  }, [commentToast])

  useEffect(() => {
    if (!row) {
      setSnippetGroupId(null)
      return
    }
    if (!editingSnippet) {
      setSnippetGroupId(row.group_id ?? row.groupId ?? null)
    }
  }, [row, editingSnippet])

  useEffect(() => {
    let ignore = false
    if (!row?.group_id) {
      setGroupDetail(null)
      return () => {}
    }
    ;(async () => {
      try {
        const detail = await getGroup(row.group_id)
        if (!ignore) setGroupDetail(detail)
      } catch (err) {
        if (!ignore) {
          if (err?.response?.status !== 404) {
            console.warn('Failed to load group detail', err)
          }
          setGroupDetail(null)
        }
      }
    })()
    return () => {
      ignore = true
    }
  }, [row?.group_id])

  const handleCommentSubmit = async (event) => {
    event.preventDefault()
    if (!user) {
      setCommentAlert({ type: 'info', message: 'Please sign in to share a comment.' })
      return
    }
    const trimmed = commentContent.trim()
    if (!trimmed) {
      setCommentError('Please enter a comment before submitting.')
      return
    }

    setSubmittingComment(true)
    setCommentError(null)
    setCommentAlert(null)
    try {
      const newComment = await createSnippetComment(id, { content: trimmed })
      setCommentContent('')
      setComments((prev) => [newComment, ...prev])
      setCommentAlert(null)
      setCommentToast({ type: 'success', message: 'Comment posted.' })
    } catch (err) {
      console.error('Failed to post comment', err)
      setCommentAlert({ type: 'danger', message: 'Failed to post comment. Please try again.' })
    } finally {
      setSubmittingComment(false)
    }
  }

  const handleVote = async (commentId, nextVote) => {
    if (!user) {
      setCommentAlert({ type: 'info', message: 'Sign in to vote on comments.' })
      return
    }
    setVoting((prev) => ({ ...prev, [commentId]: true }))
    try {
      const updated = await voteComment(commentId, { vote: nextVote })
      setComments((prev) => prev.map((item) => (item.id === commentId ? updated : item)))
    } catch (err) {
      console.error('Failed to update vote', err)
    } finally {
      setVoting((prev) => {
        const next = { ...prev }
        delete next[commentId]
        return next
      })
    }
  }

  const handleSnippetEditStart = () => {
    if (!row) return
    setSnippetAlert(null)
    setShowSnippetReport(false)
    setSnippetReportReason('')
    setSnippetReportSubmitting(false)
    setSnippetForm({
      date_read: row.date_read || '',
      book_name: row.book_name || '',
      book_author: row.book_author || '',
      page_number: row.page_number != null ? String(row.page_number) : '',
      chapter: row.chapter || '',
      verse: row.verse || '',
      text_snippet: row.text_snippet || '',
      thoughts: row.thoughts || '',
      visibility: row.visibility || 'public',
    })
    setSnippetTags((row.tags || []).map((tag) => tag.name))
    setSnippetGroupId(row.group_id ?? row.groupId ?? null)
    setEditingSnippet(true)
  }

  const handleSnippetFormChange = (event) => {
    const { name, value } = event.target
    setSnippetForm((prev) => ({ ...prev, [name]: value }))
    if (name === 'visibility' && value === 'private') {
      setSnippetGroupId(null)
    }
  }

  const handleSnippetEditCancel = () => {
    setEditingSnippet(false)
    setSnippetForm(makeEmptySnippetForm())
    setSnippetSaving(false)
    setSnippetTags([])
    if (row) {
      setSnippetGroupId(row.group_id ?? row.groupId ?? null)
    } else {
      setSnippetGroupId(null)
    }
  }

  const handleSnippetEditSubmit = async (event) => {
    event.preventDefault()
    if (!row) return
    setSnippetAlert(null)

    const trimmedPage = snippetForm.page_number.trim()
    let pageNumber = null
    if (trimmedPage !== '') {
      const parsed = Number(trimmedPage)
      if (Number.isNaN(parsed)) {
        setSnippetAlert({ type: 'danger', message: 'Page number must be a number.' })
        return
      }
      pageNumber = parsed
    }

    const payload = {
      date_read: snippetForm.date_read || null,
      book_name: snippetForm.book_name || null,
      book_author: snippetForm.book_author || null,
      page_number: pageNumber,
      chapter: snippetForm.chapter || null,
      verse: snippetForm.verse || null,
      text_snippet: snippetForm.text_snippet || null,
      thoughts: snippetForm.thoughts || null,
      tags: snippetTags,
      visibility: snippetForm.visibility || 'public',
      group_id:
        snippetForm.visibility === 'private' || snippetGroupId == null ? null : snippetGroupId,
    }

    setSnippetSaving(true)
    const previous = row
    try {
      const updated = await updateSnippet(row.id, payload)
      setRow(updated)
      setSnippetGroupId(updated.group_id ?? updated.groupId ?? null)
      setSnippetAlert({ type: 'success', message: 'Snippet updated.' })
      setEditingSnippet(false)
      setSnippetForm(makeEmptySnippetForm())
      setSnippetTags([])
      if (updated) {
        const changedFields = new Set()
        if ((previous?.date_read || null) !== (updated.date_read || null)) changedFields.add('date_read')
        if ((previous?.book_name || '').trim() !== (updated.book_name || '').trim()) changedFields.add('book_name')
        if ((previous?.book_author || '').trim() !== (updated.book_author || '').trim()) changedFields.add('book_author')
        if ((previous?.page_number || null) !== (updated.page_number || null)) changedFields.add('page_number')
        if ((previous?.chapter || '').trim() !== (updated.chapter || '').trim()) changedFields.add('chapter')
        if ((previous?.verse || '').trim() !== (updated.verse || '').trim()) changedFields.add('verse')
        if ((previous?.text_snippet || '').trim() !== (updated.text_snippet || '').trim()) changedFields.add('text_snippet')
        if ((previous?.thoughts || '').trim() !== (updated.thoughts || '').trim()) changedFields.add('thoughts')
        if ((previous?.visibility || 'public') !== (updated.visibility || 'public')) changedFields.add('visibility')
        if ((previous?.group_id ?? null) !== (updated.group_id ?? null)) changedFields.add('group_id')
        const prevTags = Array.isArray(previous?.tags)
          ? previous.tags.map((tag) => (typeof tag === 'string' ? tag : tag.name)).sort()
          : []
        const nextTags = Array.isArray(updated.tags)
          ? updated.tags.map((tag) => (typeof tag === 'string' ? tag : tag.name)).sort()
          : []
        if (prevTags.join('|') !== nextTags.join('|')) changedFields.add('tags')
        if (changedFields.size > 0) {
          capture({
            event: 'snippet_edited',
            props: {
              changed_fields: Array.from(changedFields),
              source: 'web'
            }
          })
        }
      }
    } catch (err) {
      const detail = err?.response?.data?.detail
      setSnippetAlert({ type: 'danger', message: detail || 'Failed to update snippet.' })
    } finally {
      setSnippetSaving(false)
    }
  }

  const handleSnippetDelete = async () => {
    if (!row) return
    if (!window.confirm('Delete this snippet? This cannot be undone.')) {
      return
    }
    setSnippetAlert(null)
    setDeletingSnippet(true)
    const snippetId = row.id
    try {
      await deleteSnippet(row.id)
      capture({
        event: 'snippet_deleted',
        props: {
          snippet_id: snippetId,
          source: 'web'
        }
      })
      navigate('/', { replace: true })
    } catch (err) {
      const detail = err?.response?.data?.detail
      setSnippetAlert({ type: 'danger', message: detail || 'Failed to delete snippet.' })
    } finally {
      setDeletingSnippet(false)
    }
  }

  const handleSnippetReportToggle = () => {
    setSnippetAlert(null)
    setSnippetReportReason('')
    setSnippetReportSubmitting(false)
    setShowSnippetReport((prev) => !prev)
  }

  const handleSnippetReportSubmit = async (event) => {
    event.preventDefault()
    if (!row) return
    setSnippetAlert(null)
    setSnippetReportSubmitting(true)
    try {
      const reason = snippetReportReason.trim()
      await reportSnippet(row.id, { reason: reason || null })
      setSnippetAlert({ type: 'success', message: 'Report submitted. Thank you for helping moderate!' })
      setShowSnippetReport(false)
      setSnippetReportReason('')
    } catch (err) {
      const detail = err?.response?.data?.detail
      setSnippetAlert({ type: 'danger', message: detail || 'Failed to submit report.' })
    } finally {
      setSnippetReportSubmitting(false)
    }
  }

  const handleStartEditComment = (comment) => {
    setCommentAlert(null)
    setReportingCommentId(null)
    setCommentReportReason('')
    setCommentReportSubmitting(false)
    setEditingCommentId(comment.id)
    setCommentEditContent(comment.content)
    setCommentEditError(null)
  }

  const handleCancelCommentEdit = () => {
    setEditingCommentId(null)
    setCommentEditContent('')
    setCommentEditError(null)
    setCommentSavingEdit(false)
  }

  const handleSaveCommentEdit = async (event) => {
    event.preventDefault()
    if (!editingCommentId) return
    const trimmed = commentEditContent.trim()
    if (!trimmed) {
      setCommentEditError('Please enter some content before saving.')
      return
    }

    setCommentEditError(null)
    setCommentSavingEdit(true)
    try {
      const updated = await updateComment(editingCommentId, { content: trimmed })
      setComments((prev) => prev.map((item) => (item.id === editingCommentId ? updated : item)))
      setCommentAlert(null)
      setCommentToast({ type: 'success', message: 'Comment updated.' })
      handleCancelCommentEdit()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setCommentEditError(detail || 'Failed to update comment.')
    } finally {
      setCommentSavingEdit(false)
    }
  }

  const handleDeleteComment = async (commentId) => {
    if (!window.confirm('Delete this comment?')) {
      return
    }
    setCommentAlert(null)
    setDeletingCommentId(commentId)
    try {
      await deleteComment(commentId)
      setComments((prev) => prev.filter((item) => item.id !== commentId))
      if (editingCommentId === commentId) {
        handleCancelCommentEdit()
      }
      if (reportingCommentId === commentId) {
        setReportingCommentId(null)
        setCommentReportReason('')
        setCommentReportSubmitting(false)
      }
      setCommentAlert(null)
      setCommentToast({ type: 'success', message: 'Comment deleted.' })
    } catch (err) {
      const detail = err?.response?.data?.detail
      setCommentAlert({ type: 'danger', message: detail || 'Failed to delete comment.' })
    } finally {
      setDeletingCommentId(null)
    }
  }

  const handleToggleReportComment = (commentId) => {
    setCommentAlert(null)
    setCommentReportSubmitting(false)
    if (reportingCommentId === commentId) {
      setReportingCommentId(null)
      setCommentReportReason('')
    } else {
      setReportingCommentId(commentId)
      setCommentReportReason('')
      if (editingCommentId === commentId) {
        handleCancelCommentEdit()
      }
    }
  }

  const handleCommentReportSubmit = async (event) => {
    event.preventDefault()
    if (!reportingCommentId) return
    setCommentAlert(null)
    setCommentReportSubmitting(true)
    try {
      const reason = commentReportReason.trim()
      await reportComment(reportingCommentId, { reason: reason || null })
      setCommentAlert(null)
      setCommentToast({
        type: 'success',
        message: 'Report submitted. Moderators will review it shortly.',
      })
      setReportingCommentId(null)
      setCommentReportReason('')
    } catch (err) {
      const detail = err?.response?.data?.detail
      setCommentAlert({ type: 'danger', message: detail || 'Failed to submit report.' })
    } finally {
      setCommentReportSubmitting(false)
    }
  }

  const handleCopyWithCitation = useCallback(async () => {
    if (!row) return
    const snippetText = (row.text_snippet || '').trim()
    if (!snippetText) {
      setCommentToast({ type: 'danger', message: 'There is no snippet text to copy yet.' })
      return
    }
    const authorName = (row.book_author || row.author || row.created_by_username || '').trim()
    const bookName = (row.book_name || '').trim()
    const pageNumber = row.page_number
    const citationAuthor = authorName || 'Unknown author'
    let citation = `“${snippetText}” —${citationAuthor}`
    if (bookName) {
      citation += `, ${bookName}`
    }
    if (pageNumber != null && pageNumber !== '') {
      citation += ` (p. ${pageNumber})`
    }
    citation += '.'

    const fallbackCopy = (text) => {
      if (typeof document === 'undefined') return false
      try {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.setAttribute('readonly', '')
        textarea.style.position = 'absolute'
        textarea.style.left = '-9999px'
        document.body.appendChild(textarea)
        textarea.select()
        const successful = document.execCommand('copy')
        document.body.removeChild(textarea)
        return successful
      } catch (err) {
        return false
      }
    }

    try {
      const clipboardAvailable =
        typeof navigator !== 'undefined' &&
        navigator.clipboard &&
        typeof navigator.clipboard.writeText === 'function'
      if (clipboardAvailable) {
        await navigator.clipboard.writeText(citation)
      } else {
        const success = fallbackCopy(citation)
        if (!success) {
          throw new Error('Copy not supported')
        }
      }
      setCommentToast({ type: 'success', message: 'Copied with citation.' })
    } catch (err) {
      setCommentToast({ type: 'danger', message: 'Unable to copy to clipboard. Please copy manually.' })
    }
  }, [row, setCommentToast])

  if (loading) return <div>Loading…</div>
  if (!row) return <div>Not found.</div>

  const canManageSnippet = user && (row.created_by_user_id === user.id || canModerate)

  const handleSnippetActionButton = editingSnippet ? handleSnippetEditCancel : handleSnippetEditStart
  const handleDismissCommentToast = () => setCommentToast(null)
  const commentToastVariant =
    commentToast?.type === 'success'
      ? 'success'
      : commentToast?.type === 'danger'
        ? 'danger'
        : commentToast?.type === 'info'
          ? 'info'
          : 'primary'

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
        <div className="d-flex align-items-center gap-2">
          <span className="fw-semibold">{row.book_name || 'Snippet details'}</span>
          {row.visibility === 'private' && (
            <span className="badge text-bg-warning">Private</span>
          )}
        </div>
        <div className="d-flex flex-wrap gap-2">
          <Link className="btn btn-sm btn-secondary" to="/">
            Back
          </Link>
          <button
            type="button"
            className="btn btn-sm btn-outline-warning"
            onClick={handleSnippetReportToggle}
            disabled={snippetReportSubmitting}
          >
            {showSnippetReport ? 'Cancel report' : 'Report'}
          </button>
          {canManageSnippet && (
            <button
              type="button"
              className="btn btn-sm btn-outline-primary"
              onClick={handleSnippetActionButton}
              disabled={snippetSaving}
            >
              {editingSnippet ? 'Cancel edit' : 'Edit'}
            </button>
          )}
          {canManageSnippet && (
            <button
              type="button"
              className="btn btn-sm btn-danger"
              onClick={handleSnippetDelete}
              disabled={deletingSnippet}
            >
              {deletingSnippet ? 'Deleting…' : 'Delete'}
            </button>
          )}
        </div>
      </div>
      <div className="card-body">
        {commentToast && (
          <div
            className="toast-container position-fixed bottom-0 end-0 p-3"
            style={{ zIndex: 1100 }}
          >
            <div
              className={`toast text-bg-${commentToastVariant} show`}
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              <div className="d-flex align-items-center">
                <div className="toast-body">{commentToast.message}</div>
                <button
                  type="button"
                  className="btn-close btn-close-white me-2 m-auto"
                  aria-label="Close toast"
                  onClick={handleDismissCommentToast}
                />
              </div>
            </div>
          </div>
        )}
        {snippetAlert && (
          <div className={`alert alert-${snippetAlert.type}`}>
            {snippetAlert.message}
          </div>
        )}
        {editingSnippet ? (
          <form onSubmit={handleSnippetEditSubmit} className="mb-4">
            <div className="row g-3">
              <div className="col-md-4">
                <label className="form-label">Date read (YYYY-MM-DD)</label>
                <input
                  name="date_read"
                  className="form-control"
                  value={snippetForm.date_read}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-md-8">
                <label className="form-label">Book name</label>
                <input
                  name="book_name"
                  className="form-control"
                  value={snippetForm.book_name}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Book author</label>
                <input
                  name="book_author"
                  className="form-control"
                  value={snippetForm.book_author}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Shared by</label>
                <input className="form-control" value={row.created_by_username || ''} readOnly />
              </div>
              <div className="col-md-6">
                <label className="form-label">Visibility</label>
                <select
                  name="visibility"
                  className="form-select"
                  value={snippetForm.visibility}
                  onChange={handleSnippetFormChange}
                >
                  <option value="public">Public (visible to the community)</option>
                  <option value="private">Private (only you can view)</option>
                </select>
                <div className="form-text">Private snippets stay off group feeds and discovery pages.</div>
              </div>
              <div className="col-md-6">
                <GroupSelector
                  value={snippetForm.visibility === 'private' ? null : snippetGroupId}
                  onChange={setSnippetGroupId}
                  disabled={snippetForm.visibility === 'private'}
                  helperText="Group members will be able to view and discuss the snippet."
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Page number</label>
                <input
                  name="page_number"
                  className="form-control"
                  value={snippetForm.page_number}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Chapter</label>
                <input
                  name="chapter"
                  className="form-control"
                  value={snippetForm.chapter}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Verse</label>
                <input
                  name="verse"
                  className="form-control"
                  value={snippetForm.verse}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-12">
                <label className="form-label">Text snippet</label>
                <textarea
                  name="text_snippet"
                  rows="5"
                  className="form-control"
                  value={snippetForm.text_snippet}
                  onChange={handleSnippetFormChange}
                />
              </div>
              <div className="col-12">
                <label className="form-label">Thoughts</label>
                <textarea
                  name="thoughts"
                  rows="4"
                  className="form-control"
                  value={snippetForm.thoughts}
                  onChange={handleSnippetFormChange}
                />
              </div>
            </div>
            <div className="col-12">
                <label className="form-label">Tags</label>
                <TagSelector
                  availableTags={availableTags}
                  value={snippetTags}
                  onChange={setSnippetTags}
                  allowCustom
                  placeholder="Add a tag and press Add"
                  showCounts
                />
                <div className="form-text">
                  {tagsLoading
                    ? 'Loading tag suggestions…'
                    : 'Select existing tags or add new ones to help readers find this snippet.'}
                </div>
              </div>
            <div className="mt-3 d-flex gap-2">
              <button className="btn btn-primary" type="submit" disabled={snippetSaving}>
                {snippetSaving ? 'Saving…' : 'Save changes'}
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={handleSnippetEditCancel}
                disabled={snippetSaving}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div className="row g-3 mb-4">
            <div className="col-md-4">
              <label className="form-label">Date read</label>
              <input className="form-control" value={row.date_read || ''} readOnly />
            </div>
            <div className="col-md-8">
              <label className="form-label">Book name</label>
              <input className="form-control" value={row.book_name || ''} readOnly />
            </div>
            <div className="col-md-6">
              <label className="form-label">Author</label>
              <input className="form-control" value={row.created_by_username || ''} readOnly />
            </div>
            <div className="col-md-6">
              <label className="form-label">Visibility</label>
              <input
                className="form-control"
                value={row.visibility === 'private' ? 'Private (only you can view)' : 'Public'}
                readOnly
              />
              <div className="form-text">
                {row.visibility === 'private'
                  ? 'This snippet is only visible to you.'
                  : 'Visible to the community and eligible for discovery.'}
              </div>
            </div>
            {(row.group_id || groupDetail) && (
              <div className="col-md-6">
                <label className="form-label">Group</label>
                <input
                  className="form-control"
                  value={groupDetail?.name ? `${groupDetail.name}` : `Group #${row.group_id}`}
                  readOnly
                />
                <div className="form-text">
                  {(() => {
                    const privacyValue = (groupDetail?.privacy_state || groupDetail?.privacyState || 'private').toLowerCase()
                    if (privacyValue === 'private') {
                      return 'Only members of this private group can view the snippet.'
                    }
                    if (privacyValue === 'unlisted') {
                      return 'This group is unlisted. Only members can view the shared snippets.'
                    }
                    return 'Shared in a group. Members can view and discuss the snippet.'
                  })()}
                </div>
              </div>
            )}
            <div className="col-md-3">
              <label className="form-label">Page number</label>
              <input className="form-control" value={row.page_number ?? ''} readOnly />
            </div>
            <div className="col-md-3">
              <label className="form-label">Chapter</label>
              <input className="form-control" value={row.chapter || ''} readOnly />
            </div>
            <div className="col-md-3">
              <label className="form-label">Verse</label>
              <input className="form-control" value={row.verse || ''} readOnly />
            </div>
            <div className="col-12">
              <div className="d-flex justify-content-between align-items-center">
                <label className="form-label mb-0" htmlFor={snippetTextInputId}>
                  Text snippet
                </label>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary"
                  onClick={handleCopyWithCitation}
                  disabled={!row.text_snippet}
                  title="Copy the snippet with citation"
                >
                  Copy with citation
                </button>
              </div>
              <textarea
                id={snippetTextInputId}
                className="form-control"
                rows="8"
                value={row.text_snippet || ''}
                readOnly
              />
            </div>
            <div className="col-12">
              <label className="form-label">Thoughts</label>
              <textarea className="form-control" rows="6" value={row.thoughts || ''} readOnly />
            </div>
            {row.tags && row.tags.length ? (
             <div className="col-12">
                <label className="form-label">Tags</label>
                <div className="d-flex flex-wrap gap-2">
                  {row.tags.map((tag) => (
                    <Link
                      key={tag.id}
                      className="badge bg-secondary text-decoration-none"
                      to={`/?tag=${encodeURIComponent(tag.name)}`}
                    >
                      #{tag.name}
                    </Link>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}

        {showSnippetReport && (
          <form onSubmit={handleSnippetReportSubmit} className="mb-4">
            <div className="mb-2">
              <label className="form-label" htmlFor="snippet-report">Reason (optional)</label>
              <textarea
                id="snippet-report"
                className="form-control"
                rows="3"
                value={snippetReportReason}
                onChange={(event) => setSnippetReportReason(event.target.value)}
                disabled={snippetReportSubmitting}
              />
            </div>
            <button className="btn btn-outline-warning" type="submit" disabled={snippetReportSubmitting}>
              {snippetReportSubmitting ? 'Submitting…' : 'Submit report'}
            </button>
          </form>
        )}

        <hr className="my-4" />
        <section>
          <h5 className="mb-3">Comments</h5>
          {commentAlert && (
            <div className={`alert alert-${commentAlert.type}`}>
              {commentAlert.message}
            </div>
          )}
         {!user ? (
            <div className="alert alert-info mb-4">
              Enjoying the discussion?{' '}
              <Link to="/login" className="alert-link">
                Sign in
              </Link>{' '}
              to add your thoughts and react to comments.
            </div>
          ) : (
            <form onSubmit={handleCommentSubmit} className="mb-4">
              <div className="mb-3">
                <label className="form-label" htmlFor="new-comment">
                  Leave a comment
                </label>
                <textarea
                  id="new-comment"
                  className="form-control"
                  rows="4"
                  value={commentContent}
                  onChange={(event) => {
                    if (commentError) setCommentError(null)
                    setCommentContent(event.target.value)
                  }}
                  disabled={submittingComment}
                  placeholder="Share your thoughts…"
                />
              </div>
              {commentError && <div className="text-danger mb-3">{commentError}</div>}
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submittingComment || !commentContent.trim()}
              >
                {submittingComment ? 'Posting…' : 'Post Comment'}
              </button>
            </form>
          )}
          {commentsLoading ? (
            <div>Loading comments…</div>
          ) : comments.length === 0 ? (
            <div className="text-muted">No comments yet. Be the first to comment!</div>
          ) : (
            <div className="d-flex flex-column gap-3">
              {comments.map((comment) => {
                const isVoting = !!voting[comment.id]
                const netScore = comment.upvotes - comment.downvotes
                const isEditing = editingCommentId === comment.id
                const isReporting = reportingCommentId === comment.id
                const canManageComment =
                  user && (comment.user_id === user.id || canModerate)
                return (
                  <div key={comment.id} className="border rounded p-3 d-flex flex-column flex-md-row">
                    <div className="me-md-3 mb-3 mb-md-0 text-center" style={{ minWidth: '80px' }}>
                      <button
                        type="button"
                        className={`btn btn-sm w-100 ${comment.user_vote === 1 ? 'btn-primary' : 'btn-outline-secondary'}`}
                        onClick={() => handleVote(comment.id, comment.user_vote === 1 ? 0 : 1)}
                        disabled={!user || isVoting}
                        aria-label="Upvote"
                      >
                        ▲
                      </button>
                      <div className="fw-bold my-1">{netScore}</div>
                      <button
                        type="button"
                        className={`btn btn-sm w-100 ${comment.user_vote === -1 ? 'btn-primary' : 'btn-outline-secondary'}`}
                        onClick={() => handleVote(comment.id, comment.user_vote === -1 ? 0 : -1)}
                        disabled={!user || isVoting}
                        aria-label="Downvote"
                      >
                        ▼
                      </button>
                    </div>
                    <div className="flex-grow-1">
                      <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
                        <div>
                          <span className="fw-semibold">{comment.username}</span>
                          <div className="small text-muted">
                            {new Date(comment.created_utc).toLocaleString()}
                          </div>
                        </div>
                        <div className="d-flex flex-wrap gap-2">
                          {canManageComment && !isEditing && (
                            <button
                              type="button"
                              className="btn btn-sm btn-outline-primary"
                              onClick={() => handleStartEditComment(comment)}
                            >
                              Edit
                            </button>
                          )}
                          {canManageComment && (
                            <button
                              type="button"
                              className="btn btn-sm btn-outline-danger"
                              onClick={() => handleDeleteComment(comment.id)}
                              disabled={deletingCommentId === comment.id}
                            >
                              {deletingCommentId === comment.id ? 'Deleting…' : 'Delete'}
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn-sm btn-outline-secondary"
                            onClick={() => handleToggleReportComment(comment.id)}
                            disabled={commentReportSubmitting && reportingCommentId === comment.id}
                          >
                            {isReporting ? 'Cancel report' : 'Report'}
                          </button>
                        </div>
                      </div>
                      {isEditing ? (
                        <form onSubmit={handleSaveCommentEdit}>
                          <textarea
                            className="form-control"
                            rows="3"
                            value={commentEditContent}
                            onChange={(event) => setCommentEditContent(event.target.value)}
                            disabled={commentSavingEdit}
                          />
                          {commentEditError && (
                            <div className="text-danger small mt-2">{commentEditError}</div>
                          )}
                          <div className="mt-2 d-flex gap-2">
                            <button
                              type="submit"
                              className="btn btn-sm btn-primary"
                              disabled={commentSavingEdit}
                            >
                              {commentSavingEdit ? 'Saving…' : 'Save'}
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-outline-secondary"
                              onClick={handleCancelCommentEdit}
                              disabled={commentSavingEdit}
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <p className="mb-2" style={{ whiteSpace: 'pre-wrap' }}>
                            {comment.content}
                          </p>
                          <small className="text-muted">
                            Upvotes: {comment.upvotes} · Downvotes: {comment.downvotes}
                          </small>
                        </>
                      )}
                      {isReporting && (
                        <form onSubmit={handleCommentReportSubmit} className="mt-3">
                          <label className="form-label" htmlFor={`report-${comment.id}`}>
                            Reason (optional)
                          </label>
                          <textarea
                            id={`report-${comment.id}`}
                            className="form-control"
                            rows="2"
                            value={commentReportReason}
                            onChange={(event) => setCommentReportReason(event.target.value)}
                            disabled={commentReportSubmitting}
                          />
                          <div className="mt-2 d-flex gap-2">
                            <button
                              type="submit"
                              className="btn btn-sm btn-outline-warning"
                              disabled={commentReportSubmitting}
                            >
                              {commentReportSubmitting ? 'Submitting…' : 'Submit report'}
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-outline-secondary"
                              onClick={() => handleToggleReportComment(comment.id)}
                              disabled={commentReportSubmitting}
                            >
                              Close
                            </button>
                          </div>
                        </form>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}