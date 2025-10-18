import { format, formatDistance, formatDuration, intervalToDuration, parseISO } from 'date-fns'

/**
 * Format a date string to a human-readable format
 * Example: "16th October 2025, 2:40:55 PM"
 */
export const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return 'Never'

  try {
    const date = new Date(dateString + (dateString.endsWith('Z') ? '' : 'Z'))
    const day = date.getDate()

    const getOrdinalSuffix = (d: number) => {
      if (d > 3 && d < 21) return 'th'
      switch (d % 10) {
        case 1: return 'st'
        case 2: return 'nd'
        case 3: return 'rd'
        default: return 'th'
      }
    }

    const month = date.toLocaleString('en-US', { month: 'long' })
    const year = date.getFullYear()
    const time = date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    })

    return `${day}${getOrdinalSuffix(day)} ${month} ${year}, ${time}`
  } catch (error) {
    console.error('Error formatting date:', error)
    return dateString
  }
}

/**
 * Format a date string to a shorter format
 * Example: "Oct 16, 2025"
 */
export const formatDateShort = (dateString: string | null | undefined): string => {
  if (!dateString) return 'Never'

  try {
    const date = new Date(dateString + (dateString.endsWith('Z') ? '' : 'Z'))
    return format(date, 'MMM d, yyyy')
  } catch (error) {
    console.error('Error formatting date:', error)
    return dateString
  }
}

/**
 * Format a date string to relative time
 * Example: "2 hours ago", "in 3 days"
 */
export const formatRelativeTime = (dateString: string | null | undefined): string => {
  if (!dateString) return 'Never'

  try {
    const date = new Date(dateString + (dateString.endsWith('Z') ? '' : 'Z'))
    return formatDistance(date, new Date(), { addSuffix: true })
  } catch (error) {
    console.error('Error formatting relative time:', error)
    return dateString
  }
}

/**
 * Format duration in seconds to human-readable format
 * Example: 840 minutes -> "14 hours"
 * Example: 125 seconds -> "2 min 5 sec"
 */
export const formatDurationSeconds = (seconds: number | null | undefined): string => {
  if (seconds === null || seconds === undefined || seconds === 0) return '0 sec'

  try {
    const duration = intervalToDuration({ start: 0, end: seconds * 1000 })

    const parts: string[] = []

    if (duration.years) parts.push(`${duration.years} ${duration.years === 1 ? 'year' : 'years'}`)
    if (duration.months) parts.push(`${duration.months} ${duration.months === 1 ? 'month' : 'months'}`)
    if (duration.days) parts.push(`${duration.days} ${duration.days === 1 ? 'day' : 'days'}`)
    if (duration.hours) parts.push(`${duration.hours} ${duration.hours === 1 ? 'hour' : 'hours'}`)
    if (duration.minutes) parts.push(`${duration.minutes} ${duration.minutes === 1 ? 'min' : 'min'}`)
    if (duration.seconds && parts.length < 2) parts.push(`${duration.seconds} sec`)

    return parts.slice(0, 2).join(' ') || '0 sec'
  } catch (error) {
    console.error('Error formatting duration:', error)
    return `${seconds} sec`
  }
}

/**
 * Format duration string from backend (e.g., "840 minutes" -> "14 hours")
 */
export const formatDurationString = (durationString: string | null | undefined): string => {
  if (!durationString) return '0 sec'

  try {
    // Parse backend duration strings like "840 minutes" or "5.5 seconds"
    const match = durationString.match(/^([\d.]+)\s+(second|minute|hour|day)s?$/)
    if (match) {
      const value = parseFloat(match[1])
      const unit = match[2]

      let seconds = 0
      switch (unit) {
        case 'second':
          seconds = value
          break
        case 'minute':
          seconds = value * 60
          break
        case 'hour':
          seconds = value * 3600
          break
        case 'day':
          seconds = value * 86400
          break
      }

      return formatDurationSeconds(seconds)
    }

    return durationString
  } catch (error) {
    console.error('Error formatting duration string:', error)
    return durationString
  }
}

/**
 * Format time range between two dates
 * Example: "5 min 2 sec" or "Running for 2 hours"
 */
export const formatTimeRange = (
  startTime: string | null | undefined,
  endTime?: string | null | undefined,
  status?: string
): string => {
  if (!startTime) return 'N/A'

  try {
    const start = new Date(startTime + (startTime.endsWith('Z') ? '' : 'Z'))

    if (status === 'running') {
      // Calculate duration from start to now
      const durationMs = Date.now() - start.getTime()
      const durationSec = Math.floor(durationMs / 1000)
      return `Running for ${formatDurationSeconds(durationSec)}`
    }

    if (!endTime) return 'N/A'

    const end = new Date(endTime + (endTime.endsWith('Z') ? '' : 'Z'))
    const durationMs = end.getTime() - start.getTime()
    const durationSec = Math.floor(durationMs / 1000)

    return formatDurationSeconds(durationSec)
  } catch (error) {
    console.error('Error formatting time range:', error)
    return 'N/A'
  }
}

/**
 * Format timestamp to locale string (for backward compatibility)
 */
export const formatTimestamp = (timestamp: string | null | undefined): string => {
  if (!timestamp) return 'Never'

  try {
    const date = new Date(timestamp + (timestamp.endsWith('Z') ? '' : 'Z'))
    return date.toLocaleString()
  } catch (error) {
    console.error('Error formatting timestamp:', error)
    return timestamp
  }
}

/**
 * Format bytes to human-readable format
 * Example: 1024 -> "1.00 KB"
 */
export const formatBytes = (bytes: number | null | undefined): string => {
  if (bytes === null || bytes === undefined || bytes === 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
}
