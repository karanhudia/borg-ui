import type { StoredPruneRetention } from '../../types/archives'

const UNITS: Array<[keyof StoredPruneRetention, string]> = [
  ['keep_hourly', 'h'],
  ['keep_daily', 'd'],
  ['keep_weekly', 'w'],
  ['keep_monthly', 'm'],
  ['keep_quarterly', 'q'],
  ['keep_yearly', 'y'],
]

/** One-line retention, e.g. "7d 4w 6m 1y". Empty for a missing policy. */
export function formatRetention(r: StoredPruneRetention | null | undefined): string {
  if (!r) return ''
  const parts: string[] = []
  if (r.keep_within) parts.push(`within ${r.keep_within}`)
  for (const [field, unit] of UNITS) {
    const n = Number(r[field] ?? 0)
    if (n > 0) parts.push(`${n}${unit}`)
  }
  return parts.join(' ')
}
