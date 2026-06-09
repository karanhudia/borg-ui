export function kibToUploadRatelimitMb(value?: number | null): string {
  if (!value || value <= 0) return ''
  return String(Math.round((value / 1024) * 100) / 100)
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
