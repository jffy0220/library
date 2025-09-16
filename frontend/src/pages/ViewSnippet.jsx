import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getSnippet, listSnippetComments, createSnippetComment, voteComment } from '../api'

export default function ViewSnippet() {
  const { id } = useParams()
  const [row, setRow] = useState(null)
  const [loading, setLoading] = useState(true)
  const [comments, setComments] = useState([])
  const [commentsLoading, setCommentsLoading] = useState(true)
  const [commentContent, setCommentContent] = useState('')
  const [commentError, setCommentError] = useState(null)
  const [submittingComment, setSubmittingComment] = useState(false)
  const [voting, setVoting] = useState({})

  useEffect(() => {
    let ignore = false
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
    return () => { ignore = true }
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

  const handleCommentSubmit = async (event) => {
    event.preventDefault()
    const trimmed = commentContent.trim()
    if (!trimmed) {
      setCommentError('Please enter a comment before submitting.')
      return
    }

    setSubmittingComment(true)
    setCommentError(null)
    try {
      const newComment = await createSnippetComment(id, { content: trimmed })
      setCommentContent('')
      setComments((prev) => [newComment, ...prev])
    } catch (err) {
      console.error('Failed to post comment', err)
      setCommentError('Failed to post comment. Please try again.')
    } finally {
      setSubmittingComment(false)
    }
  }

  const handleVote = async (commentId, nextVote) => {
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

  if (loading) return <div>Loading…</div>
  if (!row) return <div>Not found.</div>

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>Snippet #{row.id}</span>
        <Link className="btn btn-sm btn-secondary" to="/">Back</Link>
      </div>
      <div className="card-body">
        <div className="row g-3">
          <div className="col-md-4">
            <label className="form-label">Date read</label>
            <input className="form-control" value={row.date_read || ''} readOnly />
          </div>
          <div className="col-md-8">
            <label className="form-label">Book name</label>
            <input className="form-control" value={row.book_name || ''} readOnly />
          </div>
          <div className="col-md-6">
            <label className="form-label">User</label>
            <input className="form-control" value={row.created_by || ''} readOnly />
        </div>
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
            <label className="form-label">Text snippet</label>
            <textarea className="form-control" rows="8" value={row.text_snippet || ''} readOnly />
          </div>
          <div className="col-12">
            <label className="form-label">Thoughts</label>
            <textarea className="form-control" rows="6" value={row.thoughts || ''} readOnly />
          </div>
        </div>
        <hr className="my-4" />
        <section>
          <h5 className="mb-3">Comments</h5>
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
          {commentsLoading ? (
            <div>Loading comments…</div>
          ) : comments.length === 0 ? (
            <div className="text-muted">No comments yet. Be the first to comment!</div>
          ) : (
            <div className="d-flex flex-column gap-3">
              {comments.map((comment) => {
                const isVoting = !!voting[comment.id]
                const netScore = comment.upvotes - comment.downvotes
                return (
                  <div key={comment.id} className="border rounded p-3 d-flex">
                    <div className="me-3 text-center" style={{ minWidth: '60px' }}>
                      <button
                        type="button"
                        className={`btn btn-sm w-100 ${comment.user_vote === 1 ? 'btn-primary' : 'btn-outline-secondary'}`}
                        onClick={() => handleVote(comment.id, comment.user_vote === 1 ? 0 : 1)}
                        disabled={isVoting}
                        aria-label="Upvote"
                      >
                        ▲
                      </button>
                      <div className="fw-bold my-1">{netScore}</div>
                      <button
                        type="button"
                        className={`btn btn-sm w-100 ${comment.user_vote === -1 ? 'btn-primary' : 'btn-outline-secondary'}`}
                        onClick={() => handleVote(comment.id, comment.user_vote === -1 ? 0 : -1)}
                        disabled={isVoting}
                        aria-label="Downvote"
                      >
                        ▼
                      </button>
                    </div>
                    <div className="flex-grow-1">
                      <div className="d-flex justify-content-between align-items-baseline mb-1">
                        <span className="fw-semibold">{comment.username}</span>
                        <small className="text-muted">
                          {new Date(comment.created_utc).toLocaleString()}
                        </small>
                      </div>
                      <p className="mb-2" style={{ whiteSpace: 'pre-wrap' }}>
                        {comment.content}
                      </p>
                      <small className="text-muted">
                        Upvotes: {comment.upvotes} · Downvotes: {comment.downvotes}
                      </small>
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
