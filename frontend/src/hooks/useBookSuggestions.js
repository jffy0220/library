import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { searchBookCatalog, searchGoogleBooks } from '../api'
import useDebouncedValue from './useDebouncedValue'

const DEFAULT_LIMIT = 12
const MIN_GOOGLE_QUERY_LENGTH = 5
const DEFAULT_DEBOUNCE = 250

function formatOptions(results = [], fallbackSource = 'catalog') {
  const seen = new Set()
  return results.reduce((acc, item) => {
    if (!item) return acc
    const rawTitle = item.title || item.name || ''
    const title = typeof rawTitle === 'string' ? rawTitle.trim() : ''
    if (!title) return acc
    const rawAuthor = item.author || item.authors || ''
    let author = ''
    if (Array.isArray(rawAuthor)) {
      author = rawAuthor.filter(Boolean).join(', ')
    } else if (typeof rawAuthor === 'string') {
      author = rawAuthor.trim()
    }
    const normalizedTitle = title.toLowerCase()
    const normalizedAuthor = (author || '').toLowerCase()
    const key = `${normalizedTitle}::${normalizedAuthor}`
    if (seen.has(key)) return acc
    seen.add(key)
    acc.push({
      value: title,
      label: author ? `${title} — ${author}` : title,
      author: author || null,
      source: item.source || fallbackSource,
      isbn: item.isbn || item.isbn13 || null,
      googleVolumeId: item.googleVolumeId || item.google_volume_id || item.googleVolumeID || null
    })
    return acc
  }, [])
}

export default function useBookSuggestions(
  query,
  { limit = DEFAULT_LIMIT, minGoogleQueryLength = MIN_GOOGLE_QUERY_LENGTH, debounce = DEFAULT_DEBOUNCE } = {}
) {
  const [options, setOptions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const debouncedQuery = useDebouncedValue(query, debounce)
  const cacheRef = useRef(new Map())
  const googleStateRef = useRef({ query: '', length: 0 })
  const requestIdRef = useRef(0)
  const [retryToken, setRetryToken] = useState(0)

  const retry = useCallback(() => {
    setRetryToken((token) => token + 1)
  }, [])

  useEffect(() => {
    const raw = (debouncedQuery || '').trim()
    const lower = raw.toLowerCase()
    if (!raw) {
      setOptions([])
      setError(null)
      setLoading(false)
      googleStateRef.current = { query: '', length: 0 }
      return
    }

    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    let cancelled = false

    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const catalogKey = `catalog:${lower}`
        let catalogResults = cacheRef.current.get(catalogKey)
        if (!catalogResults) {
          catalogResults = await searchBookCatalog({ q: raw, limit })
          cacheRef.current.set(catalogKey, catalogResults)
        }
        if (cancelled || requestIdRef.current !== requestId) return
        const catalogOptions = formatOptions(catalogResults, 'catalog')
        if (catalogOptions.length > 0) {
          setOptions(catalogOptions)
          googleStateRef.current = { query: '', length: 0 }
          setError(null)
          return
        }

        if (raw.length < minGoogleQueryLength) {
          setOptions([])
          setError(null)
          googleStateRef.current = { query: '', length: 0 }
          return
        }

        const googleKey = `google:${lower}`
        let googleResults = cacheRef.current.get(googleKey)
        if (!googleResults) {
          const last = googleStateRef.current
          let baselineLength = 0
          if (
            last.query &&
            raw.toLowerCase().startsWith(last.query.toLowerCase()) &&
            last.length >= minGoogleQueryLength
          ) {
            baselineLength = last.length
          }
          if (baselineLength >= minGoogleQueryLength && raw.length - baselineLength < 2) {
            return
          }
          googleResults = await searchGoogleBooks({ q: raw, limit })
          cacheRef.current.set(googleKey, googleResults)
        }
        if (cancelled || requestIdRef.current !== requestId) return

        googleStateRef.current = { query: raw, length: raw.length }
        const googleOptions = formatOptions(googleResults, 'google')
        setOptions(googleOptions)
        if (googleOptions.length === 0) {
          setError('No matches found. Try refining your search.')
        } else {
          setError(null)
        }
      } catch (err) {
        if (!cancelled && requestIdRef.current === requestId) {
          setError('Unable to fetch book suggestions.')
          setOptions([])
        }
      } finally {
        if (!cancelled && requestIdRef.current === requestId) {
          setLoading(false)
        }
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [debouncedQuery, limit, minGoogleQueryLength, retryToken])

  const optionsWithFallback = useMemo(() => options, [options])

  return {
    options: optionsWithFallback,
    loading,
    error,
    retry
  }
}
