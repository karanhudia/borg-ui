export function isActiveRun(status?: string): boolean {
  return status === 'pending' || status === 'running'
}

export function formatRunStatus(status?: string): string {
  if (!status) return 'Unknown'
  return status.replace(/_/g, ' ')
}
