export const MIN_FILES = 100_000
export const MAX_FILES = 50_000_000
export const MIN_MEMORY = 100
export const MAX_MEMORY = 16384
export const MIN_TIMEOUT = 10
export const MAX_TIMEOUT = 86400
export const MAX_STATS_REFRESH = 1440
export const MAX_SCHEDULE_CONCURRENCY = 64

export const formatTimeout = (seconds: number): string => {
  if (seconds >= 3600) {
    const hours = seconds / 3600
    return `${hours.toFixed(1)} hour${hours !== 1 ? 's' : ''}`
  } else if (seconds >= 60) {
    const minutes = seconds / 60
    return `${minutes.toFixed(0)} minute${minutes !== 1 ? 's' : ''}`
  }
  return `${seconds} second${seconds !== 1 ? 's' : ''}`
}
