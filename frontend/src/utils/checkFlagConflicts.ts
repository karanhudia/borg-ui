export const FULL_CHECK_REQUIRED_FLAGS = ['--verify-data', '--repair', '--archives-only'] as const

export function findFullCheckRequiredFlags(extraFlags: string): string[] {
  if (!extraFlags.trim()) return []

  const found: string[] = []
  for (const token of extraFlags.trim().split(/\s+/)) {
    const option = token.split('=', 1)[0]
    if (FULL_CHECK_REQUIRED_FLAGS.includes(option as (typeof FULL_CHECK_REQUIRED_FLAGS)[number])) {
      if (!found.includes(option)) found.push(option)
    }
  }
  return found
}

export function hasPartialCheckDuration(maxDuration: number): boolean {
  return Number.isFinite(maxDuration) && maxDuration > 0
}

export function getCheckFlagDurationConflict(extraFlags: string, maxDuration: number): string[] {
  if (!hasPartialCheckDuration(maxDuration)) return []
  return findFullCheckRequiredFlags(extraFlags)
}

export function formatCheckFlagList(flags: string[]): string {
  return flags.join(', ')
}
