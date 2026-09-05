import type { ArchiveRow } from '../../types/archives'
import { parseBackendDate } from '../../utils/dateUtils'

export type HeatmapScale = 'days' | 'hours'
export const HOURLY_WEEKS = 4
const STORAGE_KEY = 'archives-heatmap-scale'

// A repository that runs more than once a day on its active days is read
// better hour by hour. Anything else stays on the year calendar.
export function suggestScale(archives: ArchiveRow[], now = new Date()): HeatmapScale {
  const since = now.getTime() - HOURLY_WEEKS * 7 * 24 * 3600 * 1000
  const days = new Map<string, number>()
  for (const archive of archives) {
    const start = parseBackendDate(archive.start)
    if (start.getTime() < since) continue
    const key = `${start.getFullYear()}-${start.getMonth()}-${start.getDate()}`
    days.set(key, (days.get(key) ?? 0) + 1)
  }
  if (days.size === 0) return 'days'
  const total = [...days.values()].reduce((sum, n) => sum + n, 0)
  return total / days.size > 1.5 ? 'hours' : 'days'
}

export function readStoredScale(): HeatmapScale | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'days' || value === 'hours' ? value : null
  } catch {
    return null
  }
}

export function storeScale(scale: HeatmapScale) {
  try {
    localStorage.setItem(STORAGE_KEY, scale)
  } catch {
    // Storage can be unavailable; the choice then lasts for the session.
  }
}
