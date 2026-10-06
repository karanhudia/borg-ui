export function kibToUploadRatelimitMb(value?: number | null): string {
  if (!value || value <= 0) return ''
  const mb = value / 1024
  return mb.toFixed(3).replace(/\.?0+$/, '')
}

export function uploadRatelimitMbToKib(value: string): number | null {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return Math.round(parsed * 1024)
}

export function formatUploadRatelimit(value?: number | null): string | null {
  const mb = kibToUploadRatelimitMb(value)
  return mb ? `${mb} MB/s` : null
}

/** Borg 2 has no --upload-ratelimit (removed in 2.0.0b22); a Borg 2
 * repository behind rclone takes the limit as rclone's bandwidth limit. */
export function uploadRatelimitSupported(borgVersion?: number | null, path?: string | null) {
  return borgVersion !== 2 || (path ?? '').startsWith('rclone:')
}
