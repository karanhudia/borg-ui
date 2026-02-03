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
        case 1:
          return 'st'
        case 2:
          return 'nd'
        case 3:
          return 'rd'
        default:
          return 'th'
      }
    }

    const month = date.toLocaleString('en-US', { month: 'long' })
    const year = date.getFullYear()
    const time = date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
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
    if (duration.months)
      parts.push(`${duration.months} ${duration.months === 1 ? 'month' : 'months'}`)
    if (duration.days) parts.push(`${duration.days} ${duration.days === 1 ? 'day' : 'days'}`)
    if (duration.hours) parts.push(`${duration.hours} ${duration.hours === 1 ? 'hour' : 'hours'}`)
    if (duration.minutes)
      parts.push(`${duration.minutes} ${duration.minutes === 1 ? 'min' : 'min'}`)
    if (duration.seconds && parts.length < 2) parts.push(`${duration.seconds} sec`)

    return parts.slice(0, 2).join(' ') || '0 sec'
  } catch (error) {
    console.error('Error formatting duration:', error)
    return `${seconds} sec`
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
 * Calculate elapsed time from a start date to now
 * Example: "2025-11-09T14:56:53Z" -> "Running for 2 hours"
 */
export const formatElapsedTime = (startTime: string | null | undefined): string => {
  if (!startTime) return ''

  try {
    const start = new Date(startTime)
    const durationMs = Date.now() - start.getTime()
    const durationSec = Math.floor(durationMs / 1000)

    return `Running for ${formatDurationSeconds(durationSec)}`
  } catch (error) {
    console.error('Error formatting elapsed time:', error)
    return ''
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
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)

  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
}

/**
 * Parse a human-readable size string back to bytes
 * Example: "1.50 GB" -> 1610612736
 * Handles formats like "1.5 GB", "1.5GB", "1,024 MB", etc.
 */
export const parseBytes = (sizeString: string | null | undefined): number | undefined => {
  if (!sizeString) return undefined

  const k = 1024
  const sizes: Record<string, number> = {
    B: 0,
    KB: 1,
    MB: 2,
    GB: 3,
    TB: 4,
    PB: 5,
  }

  // Match number (with optional decimals and commas) followed by unit
  const match = sizeString.trim().match(/^([\d,.]+)\s*(B|KB|MB|GB|TB|PB)$/i)
  if (!match) return undefined

  const value = parseFloat(match[1].replace(/,/g, ''))
  const unit = match[2].toUpperCase()

  if (isNaN(value) || !(unit in sizes)) return undefined

  return Math.round(value * Math.pow(k, sizes[unit]))
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

    // Handle hourly intervals: "0 */8 * * *" → convert to specific hours in UTC
    if (/^\d+$/.test(minute) && hour.startsWith('*/')) {
      const interval = parseInt(hour.replace('*/', ''))
      const localMinute = parseInt(minute)

      // Generate local hours: for */8 → [0, 8, 16]
      const localHours: number[] = []
      for (let h = 0; h < 24; h += interval) {
        localHours.push(h)
      }

      // Convert each local hour+minute to UTC
      const offsetMinutes = new Date().getTimezoneOffset()
      const utcHours: number[] = []

      for (const localHour of localHours) {
        const totalLocalMinutes = localHour * 60 + localMinute
        let totalUTCMinutes = totalLocalMinutes + offsetMinutes

        // Handle day wrapping
        while (totalUTCMinutes < 0) totalUTCMinutes += 24 * 60
        while (totalUTCMinutes >= 24 * 60) totalUTCMinutes -= 24 * 60

        const utcHour = Math.floor(totalUTCMinutes / 60)

        // Store UTC hour (we'll use the first utcMinute for all)
        if (utcHours.length === 0) {
          // First iteration - this utcMinute will be used
          utcHours.push(utcHour)
        } else {
          utcHours.push(utcHour)
        }
      }

      // Use the minute from first conversion
      const totalLocalMinutes = localHours[0] * 60 + localMinute
      let totalUTCMinutes = totalLocalMinutes + offsetMinutes
      while (totalUTCMinutes < 0) totalUTCMinutes += 24 * 60
      while (totalUTCMinutes >= 24 * 60) totalUTCMinutes -= 24 * 60
      const utcMinute = totalUTCMinutes % 60

      // Sort and deduplicate hours
      const uniqueHours = Array.from(new Set(utcHours)).sort((a, b) => a - b)

      return `${utcMinute} ${uniqueHours.join(',')} ${day} ${month} ${dayOfWeek}`
    }

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

    // Handle specific hours that represent intervals: "30 2,10,18 * * *" → "0 */8 * * *"
    if (
      /^\d+$/.test(minute) &&
      /^[\d,]+$/.test(hour) &&
      day === '*' &&
      month === '*' &&
      dayOfWeek === '*'
    ) {
      const utcHours = hour
        .split(',')
        .map((h) => parseInt(h))
        .sort((a, b) => a - b)

      // Check if hours form an interval pattern
      if (utcHours.length > 1) {
        const interval = utcHours[1] - utcHours[0]
        let isInterval = true

        // Verify all hours follow the interval
        for (let i = 0; i < utcHours.length - 1; i++) {
          if (utcHours[i + 1] - utcHours[i] !== interval) {
            isInterval = false
            break
          }
        }

        // Also check if first hour + interval wraps correctly to first hour
        if (isInterval && utcHours.length > 0) {
          const expectedHours = []
          for (let h = 0; h < 24; h += interval) {
            expectedHours.push(h)
          }

          // Convert each UTC hour back to local to check pattern
          const offsetMinutes = new Date().getTimezoneOffset()
          const utcMinute = parseInt(minute)
          const localHours: number[] = []

          for (const utcHour of utcHours) {
            const totalUTCMinutes = utcHour * 60 + utcMinute
            let totalLocalMinutes = totalUTCMinutes - offsetMinutes

            while (totalLocalMinutes < 0) totalLocalMinutes += 24 * 60
            while (totalLocalMinutes >= 24 * 60) totalLocalMinutes -= 24 * 60

            localHours.push(Math.floor(totalLocalMinutes / 60))
          }

          const sortedLocalHours = localHours.sort((a, b) => a - b)

          // Check if local hours form an interval starting at 0
          if (sortedLocalHours.length > 1) {
            const localInterval = sortedLocalHours[1] - sortedLocalHours[0]
            let isLocalInterval = sortedLocalHours[0] === 0

            for (let i = 0; i < sortedLocalHours.length - 1; i++) {
              if (sortedLocalHours[i + 1] - sortedLocalHours[i] !== localInterval) {
                isLocalInterval = false
                break
              }
            }

            if (isLocalInterval) {
              // Get local minute from first hour conversion
              const totalUTCMinutes = utcHours[0] * 60 + utcMinute
              let totalLocalMinutes = totalUTCMinutes - offsetMinutes
              while (totalLocalMinutes < 0) totalLocalMinutes += 24 * 60
              while (totalLocalMinutes >= 24 * 60) totalLocalMinutes -= 24 * 60
              const localMinute = totalLocalMinutes % 60

              return `${localMinute} */${localInterval} ${day} ${month} ${dayOfWeek}`
            }
          }
        }
      }

      // Not an interval pattern, fall through to normal hour conversion
    }

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
    const totalUTCMinutes = utcHours * 60 + utcMinutes

    // Add offset (to convert from UTC to local) -- Note: getTimezoneOffset is (UTC - Local), so Local = UTC - offset
    // wait: if offset is -330 (India), Local = UTC - (-330) = UTC + 330. This is correct.
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

    // Determine if we crossed day boundary relative to UTC
    let dayAdjustment = 0
    if (totalUTCMinutes - offsetMinutes < 0) {
      dayAdjustment = -1
    } else if (totalUTCMinutes - offsetMinutes >= 24 * 60) {
      dayAdjustment = 1
    }

    // If day adjustment is needed and day/dayOfWeek are specific, adjust them
    let newDay = day
    let newDayOfWeek = dayOfWeek

    if (dayAdjustment !== 0) {
      // If day is specific number, adjust it
      if (/^\d+$/.test(day)) {
        let dayNum = parseInt(day) + dayAdjustment
        if (dayNum < 1) dayNum = 1 // Logic flaw: can't easily roll back month days, simplifed: clamp or ignore for now as monthly cron is complex
        // Actually for monthly 'day' (1-31), wrapping is hard without knowing month/year.
        // For simplicity in this context (usually weekly/daily), we focus on dayOfWeek.
        if (dayNum > 31) dayNum = 31
        newDay = dayNum.toString()
      }

      // If dayOfWeek is specific, adjust it
      if (/^\d+$/.test(dayOfWeek)) {
        // Cron day 0 is Sunday, 1..6.
        // Javascript % can be negative, so (a % n + n) % n
        let dowNum = parseInt(dayOfWeek) + dayAdjustment
        dowNum = ((dowNum % 7) + 7) % 7
        newDayOfWeek = dowNum.toString()
      } else if (/^[\d,]+$/.test(dayOfWeek)) {
        // Handle lists like 1,3,5
        newDayOfWeek = dayOfWeek
          .split(',')
          .map((d) => {
            let dowNum = parseInt(d) + dayAdjustment
            dowNum = ((dowNum % 7) + 7) % 7
            return dowNum
          })
          .join(',')
      }
    }

    return `${localMinutes} ${localHours} ${newDay} ${month} ${newDayOfWeek}`
  } catch (error) {
    console.error('Error converting cron to local:', error)
    return cronExpression
  }
}

/**
 * Format a date string to full datetime with timezone
 * Example: "2025-11-09T14:56:53Z" -> "November 9, 2025 at 2:56:53 PM UTC"
 */
export const formatDateTimeFull = (dateString: string | null | undefined): string => {
  if (!dateString) return 'Never'

  try {
    const date = new Date(dateString)

    // Format: "November 9, 2025 at 2:56:53 PM UTC"
    return format(date, "MMMM d, yyyy 'at' h:mm:ss a 'UTC'")
  } catch (error) {
    console.error('Error formatting full datetime:', error)
    return dateString
  }
}

/**
 * Format a date string to compact format for tables/lists
 * Example: "2025-11-09T14:56:53Z" -> "9 Nov 2025, 2:56 PM"
 */
export const formatDateCompact = (dateString: string | null | undefined): string => {
  if (!dateString) return 'Never'

  try {
    const date = new Date(dateString)
    // Format: "17 Oct 2025, 2:13 PM" (no seconds, abbreviated month)
    return format(date, 'd MMM yyyy, h:mm a')
  } catch (error) {
    console.error('Error formatting compact date:', error)
    return dateString
  }
}
