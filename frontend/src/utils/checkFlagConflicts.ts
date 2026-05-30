export const FULL_CHECK_REQUIRED_FLAGS = ['--verify-data', '--repair', '--archives-only'] as const

function splitShellLikeFlags(extraFlags: string): string[] | null {
  const tokens: string[] = []
  let token = ''
  let quote: '"' | "'" | null = null
  let escaped = false
  let tokenStarted = false

  for (const char of extraFlags.trim()) {
    if (escaped) {
      token += char
      escaped = false
      continue
    }

    if (char === '\\' && quote !== "'") {
      escaped = true
      tokenStarted = true
      continue
    }

    if (quote) {
      if (char === quote) {
        quote = null
      } else {
        token += char
      }
      tokenStarted = true
      continue
    }

    if (char === '"' || char === "'") {
      quote = char
      tokenStarted = true
      continue
    }

    if (/\s/.test(char)) {
      if (tokenStarted) {
        tokens.push(token)
        token = ''
        tokenStarted = false
      }
      continue
    }

    token += char
    tokenStarted = true
  }

  if (quote || escaped) return null
  if (tokenStarted) tokens.push(token)
  return tokens
}

export function findFullCheckRequiredFlags(extraFlags: string): string[] {
  if (!extraFlags.trim()) return []

  const tokens = splitShellLikeFlags(extraFlags)
  if (!tokens) return []

  const found = new Set<string>()
  for (const token of tokens) {
    const option = token.split('=', 1)[0]
    if (FULL_CHECK_REQUIRED_FLAGS.includes(option as (typeof FULL_CHECK_REQUIRED_FLAGS)[number])) {
      found.add(option)
    }
  }
  return Array.from(found)
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
