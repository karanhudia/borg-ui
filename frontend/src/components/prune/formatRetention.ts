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

type AnyRetention =
  StoredPruneRetention | (Omit<StoredPruneRetention, 'keep_within'> & { keep_within: string })

/** A retention as one string, field by field in a fixed order: two policies
 * that `sameRetention` calls equal produce the same key, whatever order their
 * object literals list the fields in. */
export function retentionKey(r: AnyRetention): string {
  return [...UNITS.map(([field]) => Number(r[field] ?? 0)), r.keep_within || ''].join('|')
}

/** Field by field, so key order and '' versus null for keep_within do not matter. */
export function sameRetention(
  a: AnyRetention | null | undefined,
  b: AnyRetention | null | undefined
): boolean {
  if (!a || !b) return false
  return (
    UNITS.every(([field]) => Number(a[field] ?? 0) === Number(b[field] ?? 0)) &&
    (a.keep_within || '') === (b.keep_within || '')
  )
}
