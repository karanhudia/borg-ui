import { useEffect, useState } from 'react'
import { formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'

// A once-a-second clock, only ticking while something is running, so
// elapsed times on the board stay live without re-rendering idle rows.
export function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [active])
  return now
}

export function elapsedSince(startedAt: string | null, now: number): string {
  if (!startedAt) return ''
  const seconds = Math.max(0, Math.floor((now - parseBackendDate(startedAt).getTime()) / 1000))
  return formatDurationSeconds(seconds)
}
