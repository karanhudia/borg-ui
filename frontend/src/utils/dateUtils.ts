import { format, formatDistance, intervalToDuration } from 'date-fns'

/**
 * Format a date string to a human-readable format
 * Example: "16th October 2025, 2:40:55 PM"
 */
export const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return 'Never'

  try {
    const date = new Date(dateString)
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
    const date = new Date(dateString)
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
    const date = new Date(dateString)
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
 * Smart duration formatter that handles both duration strings and timestamps
 * If given a timestamp and start time, calculates the duration
 * If given a duration string, formats it nicely
 */
export const formatSmartDuration = (
  durationOrEndTime: string | null | undefined,
  startTime?: string | null | undefined
): string => {
  if (!durationOrEndTime) return '0 sec'

  try {
    // Check if it looks like a timestamp (contains date format like YYYY-MM-DD or ISO format)
    const isTimestamp = /\d{4}-\d{2}-\d{2}/.test(durationOrEndTime)

    if (isTimestamp && startTime) {
      // Calculate duration between start and end times
      const start = new Date(startTime)
      const end = new Date(durationOrEndTime)
      const durationMs = end.getTime() - start.getTime()
      const durationSec = Math.floor(durationMs / 1000)
      return formatDurationSeconds(durationSec)
    } else if (isTimestamp) {
      // It's a timestamp but we don't have start time, just show it as a date
      return formatDate(durationOrEndTime)
    } else {
      // It's a duration string, format it
      return formatDurationString(durationOrEndTime)
    }
  } catch (error) {
    console.error('Error formatting smart duration:', error)
    return durationOrEndTime
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
    const start = new Date(startTime)

    if (status === 'running') {
      // Calculate duration from start to now
      const durationMs = Date.now() - start.getTime()
      const durationSec = Math.floor(durationMs / 1000)
      return `Running for ${formatDurationSeconds(durationSec)}`
    }

    if (!endTime) return 'N/A'

    const end = new Date(endTime)
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
    const date = new Date(timestamp)
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

/**
 * Convert a cron expression from local time to UTC
 * Example: "0 2 * * *" (2 AM IST) -> "30 20 * * *" (8:30 PM UTC previous day)
 */
export const convertCronToUTC = (cronExpression: string): string => {
  try {
    // Parse cron expression (minute hour day month dayOfWeek)
    const parts = cronExpression.trim().split(/\s+/)
    if (parts.length !== 5) {
      // Not a standard 5-part cron, return as-is
      return cronExpression
    }

    const [minute, hour, day, month, dayOfWeek] = parts

    // Only convert if hour and minute are specific numbers (not */ranges)
    if (!/^\d+$/.test(hour) || !/^\d+$/.test(minute)) {
      // Can't convert expressions like "*/6" or ranges
      return cronExpression
    }

    // Get timezone offset in minutes
    const now = new Date()
    const offsetMinutes = now.getTimezoneOffset() // Negative for timezones ahead of UTC

    // Convert local time to UTC
    const localMinutes = parseInt(minute)
    const localHours = parseInt(hour)
    const totalLocalMinutes = localHours * 60 + localMinutes

    // Subtract offset (because getTimezoneOffset returns UTC - local)
    let totalUTCMinutes = totalLocalMinutes + offsetMinutes

    // Handle negative time (previous day)
    while (totalUTCMinutes < 0) {
      totalUTCMinutes += 24 * 60
    }

    // Handle overflow (next day)
    while (totalUTCMinutes >= 24 * 60) {
      totalUTCMinutes -= 24 * 60
    }

    // Extract hours and minutes
    const utcMinutes = totalUTCMinutes % 60
    const utcHours = Math.floor(totalUTCMinutes / 60)
    let dayAdjustment = 0

    // Determine if we crossed day boundary
    if (totalLocalMinutes + offsetMinutes < 0) {
      dayAdjustment = -1
    } else if (totalLocalMinutes + offsetMinutes >= 24 * 60) {
      dayAdjustment = 1
    }

    // If day adjustment is needed and day/dayOfWeek are specific, adjust them
    let newDay = day
    let newDayOfWeek = dayOfWeek

    if (dayAdjustment !== 0) {
      // If day is specific number, adjust it
      if (/^\d+$/.test(day)) {
        let dayNum = parseInt(day) + dayAdjustment
        if (dayNum < 1) dayNum = 1
        if (dayNum > 31) dayNum = 31
        newDay = dayNum.toString()
      }

      // If dayOfWeek is specific, adjust it
      if (/^\d+$/.test(dayOfWeek)) {
        let dowNum = (parseInt(dayOfWeek) + dayAdjustment + 7) % 7
        newDayOfWeek = dowNum.toString()
      }
    }

    return `${utcMinutes} ${utcHours} ${newDay} ${month} ${newDayOfWeek}`
  } catch (error) {
    console.error('Error converting cron to UTC:', error)
    return cronExpression
  }
}

/**
 * Convert a cron expression from UTC to local time (for display)
 * Example: "30 20 * * *" (8:30 PM UTC) -> "0 2 * * *" (2 AM IST next day)
 */
export const convertCronToLocal = (cronExpression: string): string => {
  try {
    // Parse cron expression
    const parts = cronExpression.trim().split(/\s+/)
    if (parts.length !== 5) {
      return cronExpression
    }

    const [minute, hour, day, month, dayOfWeek] = parts

    // Only convert if hour and minute are specific numbers
    if (!/^\d+$/.test(hour) || !/^\d+$/.test(minute)) {
      return cronExpression
    }

    // Get timezone offset in minutes
    const now = new Date()
    const offsetMinutes = now.getTimezoneOffset()

    // Convert UTC time to local
    const utcMinutes = parseInt(minute)
    const utcHours = parseInt(hour)
    let totalUTCMinutes = utcHours * 60 + utcMinutes

    // Add offset (to convert from UTC to local)
    let totalLocalMinutes = totalUTCMinutes - offsetMinutes

    // Handle negative time (previous day)
    while (totalLocalMinutes < 0) {
      totalLocalMinutes += 24 * 60
    }

    // Handle overflow (next day)
    while (totalLocalMinutes >= 24 * 60) {
      totalLocalMinutes -= 24 * 60
    }

    // Extract hours and minutes
    const localMinutes = totalLocalMinutes % 60
    const localHours = Math.floor(totalLocalMinutes / 60)

    return `${localMinutes} ${localHours} ${day} ${month} ${dayOfWeek}`
  } catch (error) {
    console.error('Error converting cron to local:', error)
    return cronExpression
  }
}
