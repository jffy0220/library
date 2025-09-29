import { useEffect, useState } from 'react'

export default function useDebouncedValue(value, delay = 200) {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedValue(value)
    }, delay)
    return () => {
      window.clearTimeout(timeout)
    }
  }, [value, delay])

  return debouncedValue
}