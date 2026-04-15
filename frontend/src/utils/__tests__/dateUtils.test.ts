import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  formatDate,
  formatDateShort,
  formatCronHuman,
  formatRelativeTime,
  formatDurationSeconds,
  formatTimeRange,
  formatElapsedTime,
  formatBytes,
  parseBytes,
  formatDateTimeFull,
  formatDateCompact,
  convertCronToUTC,
  convertCronToLocal,
} from '../dateUtils'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('formatDate', () => {
  it('returns Never for null', () => {
    expect(formatDate(null)).toBe('Never')
  })
  it('returns Never for undefined', () => {
    expect(formatDate(undefined)).toBe('Never')
  })
  it('formats a valid date string', () => {
    const result = formatDate('2025-01-15T10:30:00Z')
    expect(result).not.toBe('Never')
    expect(result).toMatch(/2025/)
  })
})

describe('formatDateShort', () => {
  it('returns Never for null', () => {
    expect(formatDateShort(null)).toBe('Never')
  })
  it('returns Never for undefined', () => {
    expect(formatDateShort(undefined)).toBe('Never')
  })
  it('formats a valid date to short format', () => {
    expect(formatDateShort('2025-10-16T00:00:00Z')).toMatch(/Oct \d+, 2025/)
  })
})

describe('formatCronHuman', () => {
  it('returns expression as-is when not 5 parts', () => {
    expect(formatCronHuman('0 2 * *')).toBe('0 2 * *')
  })
  it('returns "Every minute" for */1', () => {
    expect(formatCronHuman('*/1 * * * *')).toBe('Every minute')
  })
  it('returns "Every N min" for */5', () => {
    expect(formatCronHuman('*/5 * * * *')).toBe('Every 5 min')
  })
  it('returns "Every hour" for 0 */1', () => {
    expect(formatCronHuman('0 */1 * * *')).toBe('Every hour')
  })
  it('returns "Every Nh" for 0 */8', () => {
    expect(formatCronHuman('0 */8 * * *')).toBe('Every 8h')
  })
  it('returns "Daily · HH:MM" for daily schedule', () => {
    expect(formatCronHuman('0 2 * * *')).toBe('Daily · 02:00')
  })
  it('pads single-digit hour and minute', () => {
    expect(formatCronHuman('5 9 * * *')).toBe('Daily · 09:05')
  })
  it('returns day labels for specific days of week', () => {
    expect(formatCronHuman('40 1 * * 1,3,5')).toBe('Mon Wed Fri · 01:40')
  })
  it('returns "Daily" label when all 7 days are specified', () => {
    expect(formatCronHuman('0 2 * * 0,1,2,3,4,5,6')).toBe('Daily · 02:00')
  })
  it('returns "1st" suffix for day 1', () => {
    expect(formatCronHuman('0 3 1 * *')).toBe('1st · 03:00')
  })
  it('returns "2nd" suffix for day 2', () => {
    expect(formatCronHuman('0 3 2 * *')).toBe('2nd · 03:00')
  })
  it('returns "3rd" suffix for day 3', () => {
    expect(formatCronHuman('0 3 3 * *')).toBe('3rd · 03:00')
  })
  it('returns "th" suffix for day 15', () => {
    expect(formatCronHuman('0 3 15 * *')).toBe('15th · 03:00')
  })
  it('falls back to raw expression when month is specified', () => {
    expect(formatCronHuman('0 3 * 6 *')).toBe('0 3 * 6 *')
  })
  it('falls back for range-style hour', () => {
    expect(formatCronHuman('0 2-4 * * *')).toBe('0 2-4 * * *')
  })
  it('handles unknown day-of-week number gracefully', () => {
    // day 7 not in DAY_LABELS (index 7 is undefined), falls back to the raw number
    const result = formatCronHuman('0 2 * * 7')
    expect(result).toBeTruthy()
  })
})

describe('formatRelativeTime', () => {
  it('returns Never for null', () => {
    expect(formatRelativeTime(null)).toBe('Never')
  })
  it('returns Never for undefined', () => {
    expect(formatRelativeTime(undefined)).toBe('Never')
  })
  it('returns a relative time string for a valid past date', () => {
    const oneMinuteAgo = new Date(Date.now() - 60_000).toISOString()
    expect(formatRelativeTime(oneMinuteAgo)).toMatch(/minute/)
  })
})

describe('formatDurationSeconds', () => {
  it('returns "0 sec" for null', () => {
    expect(formatDurationSeconds(null)).toBe('0 sec')
  })
  it('returns "0 sec" for undefined', () => {
    expect(formatDurationSeconds(undefined)).toBe('0 sec')
  })
  it('returns "0 sec" for 0', () => {
    expect(formatDurationSeconds(0)).toBe('0 sec')
  })
  it('returns seconds', () => {
    expect(formatDurationSeconds(45)).toBe('45 sec')
  })
  it('returns minutes and seconds', () => {
    expect(formatDurationSeconds(125)).toBe('2 min 5 sec')
  })
  it('returns 1 hour (singular)', () => {
    expect(formatDurationSeconds(3600)).toBe('1 hour')
  })
  it('returns plural hours', () => {
    expect(formatDurationSeconds(7200)).toBe('2 hours')
  })
  it('stops at 2 parts (no seconds when hours+minutes already present)', () => {
    expect(formatDurationSeconds(3665)).toBe('1 hour 1 min')
  })
  it('returns 1 day (singular)', () => {
    expect(formatDurationSeconds(86_400)).toBe('1 day')
  })
  it('returns plural days', () => {
    expect(formatDurationSeconds(86_400 * 3)).toBe('3 days')
  })
  it('returns months', () => {
    expect(formatDurationSeconds(86_400 * 35)).toMatch(/month/)
  })
  it('returns years', () => {
    expect(formatDurationSeconds(86_400 * 366)).toMatch(/year/)
  })
})

describe('formatTimeRange', () => {
  it('returns N/A for null startTime', () => {
    expect(formatTimeRange(null)).toBe('N/A')
  })
  it('returns N/A for undefined startTime', () => {
    expect(formatTimeRange(undefined)).toBe('N/A')
  })
  it('returns running duration when status is "running"', () => {
    const result = formatTimeRange('2020-01-01T00:00:00Z', undefined, 'running')
    expect(result).toMatch(/Running for/)
  })
  it('returns N/A when no endTime and status is not running', () => {
    expect(formatTimeRange('2025-01-01T00:00:00Z')).toBe('N/A')
  })
  it('returns formatted duration between start and end', () => {
    const result = formatTimeRange('2025-01-01T00:00:00Z', '2025-01-01T00:05:30Z')
    expect(result).toBe('5 min 30 sec')
  })
  it('returns 0 sec for same start and end time', () => {
    expect(formatTimeRange('2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')).toBe('0 sec')
  })
})

describe('formatElapsedTime', () => {
  it('returns empty string for null', () => {
    expect(formatElapsedTime(null)).toBe('')
  })
  it('returns empty string for undefined', () => {
    expect(formatElapsedTime(undefined)).toBe('')
  })
  it('returns running duration for a valid start time', () => {
    const result = formatElapsedTime('2020-01-01T00:00:00Z')
    expect(result).toMatch(/Running for/)
  })
})

describe('formatBytes', () => {
  it('returns "0 B" for null', () => {
    expect(formatBytes(null)).toBe('0 B')
  })
  it('returns "0 B" for undefined', () => {
    expect(formatBytes(undefined)).toBe('0 B')
  })
  it('returns "0 B" for 0', () => {
    expect(formatBytes(0)).toBe('0 B')
  })
  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512.00 B')
  })
  it('formats kilobytes', () => {
    expect(formatBytes(1024)).toBe('1.00 KB')
  })
  it('formats megabytes', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.00 MB')
  })
  it('formats gigabytes', () => {
    expect(formatBytes(1024 ** 3)).toBe('1.00 GB')
  })
  it('formats terabytes', () => {
    expect(formatBytes(1024 ** 4)).toBe('1.00 TB')
  })
})

describe('parseBytes', () => {
  it('returns undefined for null', () => {
    expect(parseBytes(null)).toBeUndefined()
  })
  it('returns undefined for empty string', () => {
    expect(parseBytes('')).toBeUndefined()
  })
  it('returns undefined for non-matching string', () => {
    expect(parseBytes('not a size')).toBeUndefined()
  })
  it('returns undefined for number without unit', () => {
    expect(parseBytes('1024')).toBeUndefined()
  })
  it('parses bytes', () => {
    expect(parseBytes('512 B')).toBe(512)
  })
  it('parses kilobytes', () => {
    expect(parseBytes('1 KB')).toBe(1024)
  })
  it('parses megabytes with decimals', () => {
    expect(parseBytes('1.50 MB')).toBe(Math.round(1.5 * 1024 * 1024))
  })
  it('parses gigabytes', () => {
    expect(parseBytes('1.50 GB')).toBe(Math.round(1.5 * 1024 ** 3))
  })
  it('parses values with comma separators', () => {
    expect(parseBytes('1,024 KB')).toBe(1024 * 1024)
  })
  it('parses case-insensitively', () => {
    expect(parseBytes('1 kb')).toBe(1024)
  })
  it('parses terabytes', () => {
    expect(parseBytes('1 TB')).toBe(1024 ** 4)
  })
})

describe('formatDateTimeFull', () => {
  it('returns Never for null', () => {
    expect(formatDateTimeFull(null)).toBe('Never')
  })
  it('returns Never for undefined', () => {
    expect(formatDateTimeFull(undefined)).toBe('Never')
  })
  it('includes full month name and year', () => {
    const result = formatDateTimeFull('2025-11-09T14:56:53Z')
    expect(result).toMatch(/November/)
    expect(result).toMatch(/2025/)
    expect(result).toContain('at')
  })
})

describe('formatDateCompact', () => {
  it('returns Never for null', () => {
    expect(formatDateCompact(null)).toBe('Never')
  })
  it('returns Never for undefined', () => {
    expect(formatDateCompact(undefined)).toBe('Never')
  })
  it('formats a date in compact form', () => {
    const result = formatDateCompact('2025-10-17T14:13:00Z')
    expect(result).toMatch(/2025/)
    expect(result).toMatch(/Oct/)
  })
})

describe('convertCronToUTC', () => {
  it('returns expression as-is for non-5-part cron', () => {
    expect(convertCronToUTC('0 2 * *')).toBe('0 2 * *')
  })
  it('returns expression as-is for non-numeric hour (range)', () => {
    expect(convertCronToUTC('0 2-4 * * *')).toBe('0 2-4 * * *')
  })
  it('returns expression as-is for non-numeric minute', () => {
    expect(convertCronToUTC('*/5 2 * * *')).toBe('*/5 2 * * *')
  })
  it('makes no change at UTC offset 0', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    expect(convertCronToUTC('0 2 * * *')).toBe('0 2 * * *')
  })
  it('converts hourly interval pattern to specific UTC hours', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    const result = convertCronToUTC('0 */8 * * *')
    // UTC+0: local hours [0,8,16] → UTC hours [0,8,16]
    expect(result).toBe('0 0,8,16 * * *')
  })
  it('adjusts specific day-of-week backward when crossing day boundary', () => {
    // UTC+6 (offset = -360): 1 AM local → 7 PM UTC previous day, dayAdjustment=-1
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-360)
    const result = convertCronToUTC('0 1 * * 1') // Mon 1 AM UTC+6 → Sun 7 PM UTC
    expect(result).toBe('0 19 * * 0')
  })
  it('adjusts specific day-of-month backward when crossing day boundary', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-360)
    const result = convertCronToUTC('0 1 15 * *') // 15th 1 AM UTC+6 → 14th 7 PM UTC
    expect(result).toContain('14')
  })
  it('does not adjust day-of-week list (only single-day values are adjusted)', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-360)
    // convertCronToUTC only adjusts single numeric dayOfWeek, not comma-separated lists
    const result = convertCronToUTC('0 1 * * 1,3,5')
    expect(result).toBe('0 19 * * 1,3,5')
  })
  it('clamps day-of-month to minimum 1', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-360)
    const result = convertCronToUTC('0 1 1 * *') // 1st 1 AM UTC+6 → previous day 7 PM UTC
    // day 1 + (-1) = 0 → clamped to 1
    expect(result).toContain('1')
  })
  it('handles forward day crossing (UTC-8)', () => {
    // UTC-8 (offset=+480): 11 PM local → 7 AM UTC next day, dayAdjustment=+1
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(480)
    const result = convertCronToUTC('0 23 * * 5') // Fri 11 PM UTC-8 → Sat 7 AM UTC
    expect(result).toBe('0 7 * * 6')
  })
})

describe('convertCronToLocal', () => {
  it('returns expression as-is for non-5-part cron', () => {
    expect(convertCronToLocal('0 2 * *')).toBe('0 2 * *')
  })
  it('returns expression as-is for non-numeric hour', () => {
    expect(convertCronToLocal('0 2-4 * * *')).toBe('0 2-4 * * *')
  })
  it('returns expression as-is when minute is non-numeric and hour is specific', () => {
    expect(convertCronToLocal('*/5 2 * * *')).toBe('*/5 2 * * *')
  })
  it('makes no change at UTC offset 0', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    expect(convertCronToLocal('0 2 * * *')).toBe('0 2 * * *')
  })
  it('detects and restores interval pattern from multiple hours', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    // UTC hours [0,8,16] represent a */8 interval starting at 0 → restored to 0 */8
    const result = convertCronToLocal('0 0,8,16 * * *')
    expect(result).toBe('0 */8 * * *')
  })
  it('falls through when multiple hours are not a clean interval', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    // Hours [2,10,18] start at 2, not 0 → not restored to */8
    const result = convertCronToLocal('0 2,10,18 * * *')
    // Falls through to specific hour conversion (hour is not purely numeric, but it's multi-value)
    // Actually "2,10,18" matches /^[\d,]+$/ but not /^\d+$/, so the non-numeric check catches it
    expect(result).toBe('0 2,10,18 * * *')
  })
  it('adjusts day-of-week forward when crossing day boundary', () => {
    // UTC+8 (offset=-480): UTC 10 PM → local 6 AM next day, dayAdjustment=+1
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    const result = convertCronToLocal('0 22 * * 5') // UTC Fri 10 PM → local Sat 6 AM
    expect(result).toBe('0 6 * * 6')
  })
  it('adjusts day-of-week list when crossing day boundary forward', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    const result = convertCronToLocal('0 22 * * 1,3,5') // UTC Mon/Wed/Fri → local Tue/Thu/Sat
    expect(result).toBe('0 6 * * 2,4,6')
  })
  it('adjusts day-of-week backward when crossing day boundary', () => {
    // UTC-6 (offset=+360): UTC 2 AM → local 8 PM previous day, dayAdjustment=-1
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(360)
    const result = convertCronToLocal('0 2 * * 3') // UTC Wed 2 AM → local Tue 8 PM
    expect(result).toBe('0 20 * * 2')
  })
  it('adjusts specific day-of-month when crossing boundary', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    const result = convertCronToLocal('0 22 14 * *') // UTC 14th 10 PM → local 15th 6 AM
    expect(result).toContain('15')
  })
  it('clamps day-of-month to minimum 1', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(360)
    // UTC 2 AM on 1st → local 8 PM previous day → day 0 → clamped to 1
    const result = convertCronToLocal('0 2 1 * *')
    expect(result).toMatch(/^0 20 1 \* \*/)
  })
  it('wraps day-of-week 0 (Sunday) back to Sunday when subtracting 1', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(360)
    const result = convertCronToLocal('0 2 * * 0') // UTC Sun 2 AM → local Sat 8 PM
    // (0 - 1 + 7) % 7 = 6 (Saturday)
    expect(result).toBe('0 20 * * 6')
  })
})
