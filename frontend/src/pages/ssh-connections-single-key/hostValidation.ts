export type HostValidationResult =
  | { ok: true; host: string }
  | { ok: false; errorKey: 'sshConnections.validation.hostBareOnly' }

const HOST_ERROR_KEY = 'sshConnections.validation.hostBareOnly' as const
const DNS_LABEL_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/
const FORBIDDEN_HOST_CHARS = /[/\\@[\]()<>,"'`|]/

export function normalizeSshHostInput(rawHost: string): HostValidationResult {
  const host = rawHost.trim()

  if (
    !host ||
    hasHiddenOrSpaceCharacter(host) ||
    FORBIDDEN_HOST_CHARS.test(host)
  ) {
    return { ok: false, errorKey: HOST_ERROR_KEY }
  }

  if (isValidIpv4(host) || isValidIpv6(host) || isValidDnsName(host)) {
    return { ok: true, host }
  }

  return { ok: false, errorKey: HOST_ERROR_KEY }
}

function hasHiddenOrSpaceCharacter(host: string): boolean {
  return [...host].some((char) => /\s/u.test(char) || /\p{C}/u.test(char))
}

function isValidIpv4(host: string): boolean {
  const parts = host.split('.')
  if (parts.length !== 4) return false

  return parts.every((part) => {
    if (!/^\d{1,3}$/.test(part)) return false
    const value = Number(part)
    return value >= 0 && value <= 255 && String(value) === part
  })
}

function isValidIpv6(host: string): boolean {
  if (!host.includes(':') || !/^[0-9A-Fa-f:]+$/.test(host)) return false
  if (host.includes(':::')) return false

  const hasCompression = host.includes('::')
  if (!hasCompression) {
    const segments = host.split(':')
    return segments.length === 8 && segments.every(isValidIpv6Segment)
  }

  const compressedParts = host.split('::')
  if (compressedParts.length !== 2) return false

  const leftSegments = compressedParts[0] ? compressedParts[0].split(':') : []
  const rightSegments = compressedParts[1] ? compressedParts[1].split(':') : []
  const segmentCount = leftSegments.length + rightSegments.length

  return (
    segmentCount < 8 &&
    leftSegments.every(isValidIpv6Segment) &&
    rightSegments.every(isValidIpv6Segment)
  )
}

function isValidIpv6Segment(segment: string): boolean {
  return /^[0-9A-Fa-f]{1,4}$/.test(segment)
}

function isValidDnsName(host: string): boolean {
  if (host.includes(':') || host.length > 253) return false

  const normalizedHost = host.endsWith('.') ? host.slice(0, -1) : host
  if (!normalizedHost) return false

  return normalizedHost.split('.').every((label) => DNS_LABEL_PATTERN.test(label))
}
