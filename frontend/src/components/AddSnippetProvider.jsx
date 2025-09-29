import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { createSnippet, deleteSnippet, listBooks, listTags } from '../api'
import { useAuth } from '../auth'
import TagInput from './TagInput'

const AddSnippetContext = createContext(null)

function createInitialFormState() {
  return {
    text: '',
    book: '',
    page: '',
    chapter: '',
    tags: [],
    thoughts: '',
  }
}

function normalizeSuggestionList(items, getValue) {
  const seen = new Set()
  const list = []
  items.forEach((item) => {
    const raw = getValue(item)
    const value = typeof raw === 'string' ? raw.trim() : ''
    if (!value) return
    const key = value.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    list.push(value)
  })
  list.sort((a, b) => a.localeCompare(b))
  return list
}

function addSuggestionIfMissing(list, value) {
  const normalized = (value || '').trim()
  if (!normalized) return list
  const key = normalized.toLowerCase()
  if (list.some((item) => item.toLowerCase() === key)) {
    return list
  }
  const next = [...list, normalized]
  next.sort((a, b) => a.localeCompare(b))
  return next
}

export function AddSnippetProvider({ children }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [form, setForm] = useState(createInitialFormState)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [bookOptions, setBookOptions] = useState([])
  const [tagOptions, setTagOptions] = useState([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [suggestionsLoaded, setSuggestionsLoaded] = useState(false)
  const [bookSuggestionsError, setBookSuggestionsError] = useState(null)
  const [tagSuggestionsError, setTagSuggestionsError] = useState(null)
  const [toast, setToast] = useState(null)
  const dialogRef = useRef(null)
  const textFieldRef = useRef(null)
  const formRef = useRef(null)
  const previousFocusRef = useRef(null)
  const undoRef = useRef(null)
  const titleId = useId()
  const textId = useId()
  const bookId = useId()
  const pageId = useId()
  const chapterId = useId()
  const thoughtsId = useId()
  const tagsInputId = useId()
  const bookListId = `${bookId}-options`

  const resetForm = useCallback(() => {
    setForm(createInitialFormState())
    setFormError(null)
  }, [])

  const clearUndoState = useCallback(() => {
    if (undoRef.current?.timerId) {
      window.clearTimeout(undoRef.current.timerId)
    }
    undoRef.current = null
  }, [])

  useEffect(() => () => clearUndoState(), [clearUndoState])

  const handleDismissToast = useCallback(() => {
    setToast(null)
    clearUndoState()
  }, [clearUndoState])

  const handleUndo = useCallback(async () => {
    const pending = undoRef.current
    if (!pending) return
    clearUndoState()
    setToast({ message: 'Undoing snippet…', variant: 'dark', duration: null, dismissible: false })
    try {
      await deleteSnippet(pending.snippetId)
      setToast({ message: 'Snippet creation undone.', variant: 'info', duration: 4000 })
    } catch (err) {
      const detail = err?.response?.data?.detail
      setToast({ message: detail || 'Failed to undo snippet.', variant: 'danger', duration: 5000 })
    }
  }, [clearUndoState])

  const showCreationToast = useCallback(
    (snippetId) => {
      if (!snippetId) {
        setToast({ message: 'Snippet saved.', variant: 'success', duration: 4000 })
        return
      }
      clearUndoState()
      const timerId = window.setTimeout(() => {
        setToast(null)
        undoRef.current = null
      }, 5000)
      undoRef.current = { snippetId, timerId }
      setToast({
        message: 'Snippet saved.',
        variant: 'success',
        actionLabel: 'Undo',
        onAction: handleUndo,
        duration: null,
      })
    },
    [clearUndoState, handleUndo]
  )

  useEffect(() => {
    if (!toast) return undefined
    if (typeof toast.duration !== 'number') return undefined
    const timerId = window.setTimeout(() => {
      setToast(null)
    }, toast.duration)
    return () => window.clearTimeout(timerId)
  }, [toast])

  const closeModal = useCallback(() => {
    setIsOpen(false)
    setSubmitting(false)
    resetForm()
  }, [resetForm])

  const openModal = useCallback(() => {
    if (!user) {
      navigate('/login')
      return
    }
    if (isOpen) return
    resetForm()
    setSubmitting(false)
    setIsOpen(true)
  }, [user, navigate, isOpen, resetForm])

  useEffect(() => {
    if (!isOpen) return undefined
    const previouslyFocused = document.activeElement
    previousFocusRef.current = previouslyFocused

    const node = dialogRef.current
    if (!node) return undefined

    const focusFirstField = () => {
      if (textFieldRef.current) {
        textFieldRef.current.focus()
        return
      }
      const focusable = node.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length > 0) {
        focusable[0].focus()
      }
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeModal()
        return
      }
      if (event.key === 'Tab') {
        const focusable = Array.from(
          node.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        ).filter((element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true')
        if (focusable.length === 0) {
          event.preventDefault()
          return
        }
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        }
      }
    }

    const focusTimer = window.setTimeout(focusFirstField, 0)
    node.addEventListener('keydown', handleKeyDown)

    return () => {
      window.clearTimeout(focusTimer)
      node.removeEventListener('keydown', handleKeyDown)
      const previous = previousFocusRef.current
      if (previous && typeof previous.focus === 'function') {
        previous.focus()
      }
      previousFocusRef.current = null
    }
  }, [isOpen, closeModal])

  useEffect(() => {
    const handleShortcut = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        openModal()
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [openModal])

  useEffect(() => {
    if (!isOpen) return undefined
    if (suggestionsLoaded || loadingSuggestions) return undefined
    let ignore = false
    setLoadingSuggestions(true)
    setBookSuggestionsError(null)
    setTagSuggestionsError(null)
    ;(async () => {
      try {
        const [booksResult, tagsResult] = await Promise.allSettled([
          listBooks({ limit: 200 }),
          listTags({ limit: 200 }),
        ])
        if (ignore) return
        if (booksResult.status === 'fulfilled') {
        setBookOptions((prev) => {
          const fromApi = normalizeSuggestionList(booksResult.value, (item) => item?.name ?? item)
          if (fromApi.length === 0) {
            return prev
          }
          const seen = new Set(fromApi.map((name) => name.toLowerCase()))
          prev.forEach((name) => {
            const normalized = (name || '').trim()
            if (!normalized) return
            const key = normalized.toLowerCase()
            if (seen.has(key)) return
            seen.add(key)
            fromApi.push(normalized)
          })
          fromApi.sort((a, b) => a.localeCompare(b))
          return fromApi
        })
        setBookSuggestionsError(null)
      } else {
        setBookSuggestionsError('Unable to load book suggestions.')
      }
      if (tagsResult.status === 'fulfilled') {
        setTagOptions((prev) => {
          const fromApi = normalizeSuggestionList(tagsResult.value, (item) => item?.name ?? item)
          if (fromApi.length === 0) {
            return prev
          }
          const seen = new Set(fromApi.map((name) => name.toLowerCase()))
          prev.forEach((name) => {
            const normalized = (name || '').trim()
            if (!normalized) return
            const key = normalized.toLowerCase()
            if (seen.has(key)) return
            seen.add(key)
            fromApi.push(normalized)
          })
          fromApi.sort((a, b) => a.localeCompare(b))
          return fromApi
        })
        setTagSuggestionsError(null)
      } else {
        setTagSuggestionsError('Unable to load tag suggestions.')
      }
      } finally {
        if (!ignore) {
          setSuggestionsLoaded(true)
          setLoadingSuggestions(false)
        }
      }
    })()
    return () => {
      ignore = true
      setLoadingSuggestions(false)
    }
  }, [isOpen, suggestionsLoaded, loadingSuggestions])

  const handleRetrySuggestions = useCallback(() => {
    if (loadingSuggestions) return
    setSuggestionsLoaded(false)
  }, [loadingSuggestions])

  const handleFieldChange = useCallback((field) => {
    return (event) => {
      const { value } = event.target
      setForm((prev) => ({ ...prev, [field]: value }))
      if (formError) setFormError(null)
    }
  }, [formError])

  const handleTagChange = useCallback((tags) => {
    setForm((prev) => ({ ...prev, tags }))
    if (formError) setFormError(null)
  }, [formError])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return
    const trimmedText = form.text.trim()
    if (!trimmedText) {
      setFormError('Please add the snippet text before saving.')
      if (textFieldRef.current) {
        textFieldRef.current.focus()
      }
      return
    }
    const trimmedBook = form.book.trim()
    const trimmedChapter = form.chapter.trim()
    const trimmedThoughts = form.thoughts.trim()
    const pageInput = form.page.trim()
    let pageNumber = null
    if (pageInput) {
      const parsed = Number.parseInt(pageInput, 10)
      if (!Number.isFinite(parsed)) {
        setFormError('Page must be a number.')
        return
      }
      pageNumber = parsed
    }

    setSubmitting(true)
    try {
      const payload = {
        text_snippet: trimmedText,
        book_name: trimmedBook || null,
        page_number: pageNumber,
        chapter: trimmedChapter || null,
        tags: form.tags,
        thoughts: trimmedThoughts || null,
      }
      const result = await createSnippet(payload)
      setIsOpen(false)
      resetForm()
      setSubmitting(false)
      if (trimmedBook) {
        setBookOptions((prev) => addSuggestionIfMissing(prev, trimmedBook))
      }
      if (form.tags.length > 0) {
        setTagOptions((prev) => {
          let next = prev
          const seen = new Set(prev.map((tag) => tag.toLowerCase()))
          const additions = []
          form.tags.forEach((tag) => {
            const normalized = (tag || '').trim()
            if (!normalized) return
            const key = normalized.toLowerCase()
            if (seen.has(key)) return
            seen.add(key)
            additions.push(normalized)
          })
          if (additions.length === 0) return next
          next = [...next, ...additions]
          next.sort((a, b) => a.localeCompare(b))
          return next
        })
      }
      showCreationToast(result?.id)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setFormError(detail || 'Failed to save snippet. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleTextKeyDown = (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()
      if (formRef.current) {
        formRef.current.requestSubmit()
      }
    }
  }

  const contextValue = useMemo(
    () => ({
      open: openModal,
      close: closeModal,
      isOpen,
    }),
    [openModal, closeModal, isOpen]
  )

  const backdropClick = (event) => {
    if (event.target === event.currentTarget) {
      closeModal()
    }
  }

  return (
    <AddSnippetContext.Provider value={contextValue}>
      {children}
      {isOpen && (
        <div className="add-snippet-overlay" onMouseDown={backdropClick}>
          <div
            ref={dialogRef}
            className="add-snippet-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="add-snippet-dialog__header">
              <h2 className="add-snippet-dialog__title" id={titleId}>
                Add snippet
              </h2>
              <button type="button" className="btn-close btn-close-white" aria-label="Close" onClick={closeModal} />
            </div>
            <p className="text-muted small mb-4">
              Press Esc to close. Use Tab to move between fields. Submit with Enter or Ctrl/Cmd + Enter.
            </p>
            {formError && (
              <div className="alert alert-danger" role="alert">
                {formError}
              </div>
            )}
            <form ref={formRef} onSubmit={handleSubmit} className="d-flex flex-column gap-3">
              <div>
                <label className="form-label" htmlFor={textId}>
                  Snippet text
                </label>
                <textarea
                  id={textId}
                  ref={textFieldRef}
                  className="form-control"
                  rows={4}
                  value={form.text}
                  onChange={handleFieldChange('text')}
                  onKeyDown={handleTextKeyDown}
                  placeholder="Paste the highlight you want to remember"
                  required
                  disabled={submitting}
                />
              </div>

              <div>
                <label className="form-label" htmlFor={bookId}>
                  Book
                </label>
                <input
                  id={bookId}
                  className="form-control"
                  type="text"
                  list={bookListId}
                  value={form.book}
                  onChange={handleFieldChange('book')}
                  placeholder="Search existing titles or create a new one"
                  disabled={submitting}
                  autoComplete="off"
                />
                <datalist id={bookListId}>
                  {bookOptions.map((book) => (
                    <option key={book.toLowerCase()} value={book} />
                  ))}
                </datalist>
                <div className="form-text">
                  {loadingSuggestions
                    ? 'Loading book suggestions…'
                    : bookSuggestionsError || 'Autocomplete finds previous books instantly.'}
                </div>
                {bookSuggestionsError ? (
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0 mt-1"
                    onClick={handleRetrySuggestions}
                  >
                    Retry loading suggestions
                  </button>
                ) : null}
              </div>

              <div className="row g-3">
                <div className="col-sm-4">
                  <label className="form-label" htmlFor={pageId}>
                    Page
                  </label>
                  <input
                    id={pageId}
                    className="form-control"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={form.page}
                    onChange={handleFieldChange('page')}
                    placeholder="e.g. 128"
                    disabled={submitting}
                  />
                </div>
                <div className="col-sm-4">
                  <label className="form-label" htmlFor={chapterId}>
                    Chapter
                  </label>
                  <input
                    id={chapterId}
                    className="form-control"
                    type="text"
                    value={form.chapter}
                    onChange={handleFieldChange('chapter')}
                    placeholder="Optional"
                    disabled={submitting}
                  />
                </div>
                <div className="col-sm-4">
                  <label className="form-label" htmlFor={tagsInputId}>
                    Tags
                  </label>
                  <TagInput
                    inputId={tagsInputId}
                    availableTags={tagOptions}
                    value={form.tags}
                    onChange={handleTagChange}
                    disabled={submitting}
                    placeholder="Add a tag and press Enter"
                  />
                  <div className="form-text">
                    {loadingSuggestions
                      ? 'Loading tag suggestions…'
                      : tagSuggestionsError || 'Use Enter, Tab, or comma to add tags on the fly.'}
                  </div>
                  {tagSuggestionsError ? (
                    <button
                      type="button"
                      className="btn btn-link btn-sm p-0 mt-1"
                      onClick={handleRetrySuggestions}
                    >
                      Retry loading suggestions
                    </button>
                  ) : null}
                </div>
              </div>

              <div>
                <label className="form-label" htmlFor={thoughtsId}>
                  Thoughts
                </label>
                <textarea
                  id={thoughtsId}
                  className="form-control"
                  rows={3}
                  value={form.thoughts}
                  onChange={handleFieldChange('thoughts')}
                  placeholder="Capture why this matters to you (optional)"
                  disabled={submitting}
                />
              </div>

              <div className="d-flex justify-content-end gap-2 mt-2">
                <button type="button" className="btn btn-outline-secondary" onClick={closeModal} disabled={submitting}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Saving…' : 'Save snippet'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {toast && (
        <div className="toast-container position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1300 }}>
          <div
            className={`toast text-bg-${toast.variant || 'dark'} show`}
            role="status"
            aria-live="assertive"
            aria-atomic="true"
          >
            <div className="toast-body">
              <div className="d-flex flex-column flex-sm-row align-items-sm-center gap-3">
                <span className="fw-semibold">{toast.message}</span>
                <div className="d-flex gap-2 ms-sm-auto">
                  {toast.actionLabel && toast.onAction ? (
                    <button type="button" className="btn btn-sm btn-light" onClick={toast.onAction}>
                      {toast.actionLabel}
                    </button>
                  ) : null}
                  {toast.dismissible !== false ? (
                    <button
                      type="button"
                      className="btn-close btn-close-white"
                      aria-label="Close toast"
                      onClick={handleDismissToast}
                    />
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </AddSnippetContext.Provider>
  )
}

export function useAddSnippet() {
  const context = useContext(AddSnippetContext)
  if (!context) {
    throw new Error('useAddSnippet must be used within an AddSnippetProvider')
  }
  return context
}