/**
 * Tests for dateUtils.ts
 * Focus: Critical business logic that can fail silently
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  convertCronToUTC,
  convertCronToLocal,
  formatBytes,
  parseBytes,
  formatDurationSeconds,
} from './dateUtils'

describe('convertCronToUTC - Critical Edge Cases', () => {
  beforeEach(() => {
    // Mock timezone offset to UTC-5 (EST)
    // getTimezoneOffset returns UTC - local, so -5 hours = 300 minutes
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('handles midnight crossing day boundary forward (UTC-5 timezone)', () => {
    // User in UTC-5 sets 11 PM (23:00)
    // Should convert to 4 AM next day UTC (23 + 5 = 28, which wraps to 4)
    const result = convertCronToUTC('0 23 * * *')
    const parts = result.split(' ')

    expect(parts[0]).toBe('0') // minutes stay at 0
    expect(parts[1]).toBe('4') // hours: 23 + 5 = 28 -> 4 (next day)
    expect(parts[2]).toBe('*') // day should remain wildcard (can't adjust wildcards)
  })

  it('handles midnight crossing day boundary backward (UTC+5:30 timezone)', () => {
    // Mock timezone offset to UTC+5:30 (IST)
    // getTimezoneOffset returns negative for ahead of UTC
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-330)

    // User in UTC+5:30 sets 1:00 AM
    // Should convert to 7:30 PM previous day UTC (1:00 - 5:30 = -4:30 = 19:30 previous day)
    const result = convertCronToUTC('0 1 * * *')
    const parts = result.split(' ')

    expect(parts[0]).toBe('30') // minutes: 0 - 30 = -30 -> 30 (previous hour)
    expect(parts[1]).toBe('19') // hours: 1 - 6 = -5 -> 19 (previous day)
    expect(parts[2]).toBe('*') // day remains wildcard
  })

  it('preserves non-numeric expressions unchanged', () => {
    // Expressions with wildcards, ranges, or steps cannot be converted
    expect(convertCronToUTC('*/15 * * * *')).toBe('*/15 * * * *')
    expect(convertCronToUTC('0 9-17 * * 1-5')).toBe('0 9-17 * * 1-5')
    expect(convertCronToUTC('*/6 */2 * * *')).toBe('*/6 */2 * * *')
    expect(convertCronToUTC('0 */4 * * *')).toBe('0 */4 * * *')
  })

  it('round-trip conversion is identity operation (UTC-5)', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)

    const original = '30 14 * * *' // 2:30 PM local
    const utc = convertCronToUTC(original)
    const back = convertCronToLocal(utc)

    expect(back).toBe(original)
  })

  it('round-trip conversion is identity operation (UTC+5:30)', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-330)

    const original = '0 2 * * *' // 2:00 AM local
    const utc = convertCronToUTC(original)
    const back = convertCronToLocal(utc)

    expect(back).toBe(original)
  })

  it('handles edge case at noon (UTC-5)', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)

    // Noon should convert cleanly without day boundary issues
    const result = convertCronToUTC('0 12 * * *')
    const parts = result.split(' ')

    expect(parts[0]).toBe('0') // minutes
    expect(parts[1]).toBe('17') // hours: 12 + 5 = 17 (5 PM UTC)
    expect(parts[2]).toBe('*') // day should remain wildcard (no boundary crossed)
  })

  it('handles specific day numbers crossing boundaries', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)

    // 11 PM on the 15th -> 4 AM on the 16th
    const result = convertCronToUTC('0 23 15 * *')
    const parts = result.split(' ')

    expect(parts[1]).toBe('4') // hours
    expect(parts[2]).toBe('16') // day incremented
  })

  it('handles specific day of week crossing boundaries', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)

    // 11 PM on Monday (1) -> 4 AM on Tuesday (2)
    const result = convertCronToUTC('0 23 * * 1')
    const parts = result.split(' ')

    expect(parts[1]).toBe('4') // hours
    expect(parts[4]).toBe('2') // day of week incremented
  })

  it('handles day of week wrapping from Saturday to Sunday', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)

    // 11 PM on Saturday (6) -> 4 AM on Sunday (0)
    const result = convertCronToUTC('0 23 * * 6')
    const parts = result.split(' ')

    expect(parts[1]).toBe('4') // hours
    expect(parts[4]).toBe('0') // day of week wraps to Sunday
  })

  it('returns original expression if not 5 parts', () => {
    expect(convertCronToUTC('0 12 * *')).toBe('0 12 * *')
    expect(convertCronToUTC('0 0 12 * * *')).toBe('0 0 12 * * *')
    expect(convertCronToUTC('invalid')).toBe('invalid')
  })

  it('handles UTC timezone (offset = 0)', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)

    // In UTC, conversion should return the same value
    const result = convertCronToUTC('30 14 * * *')
    expect(result).toBe('30 14 * * *')
  })
})

describe('convertCronToLocal', () => {
  beforeEach(() => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('converts UTC to local time correctly', () => {
    // 5 PM UTC -> 12 PM EST (UTC-5)
    const result = convertCronToLocal('0 17 * * *')
    expect(result).toBe('0 12 * * *')
  })

  it('handles day boundary crossing backward', () => {
    // 2 AM UTC -> 9 PM previous day EST (UTC-5)
    const result = convertCronToLocal('0 2 * * *')
    expect(result).toBe('0 21 * * *')
  })

  it('preserves non-numeric expressions unchanged', () => {
    expect(convertCronToLocal('*/15 * * * *')).toBe('*/15 * * * *')
    expect(convertCronToLocal('0 9-17 * * 1-5')).toBe('0 9-17 * * 1-5')
  })

  it('returns original expression if invalid format', () => {
    expect(convertCronToLocal('invalid')).toBe('invalid')
    expect(convertCronToLocal('0 12 * *')).toBe('0 12 * *')
  })
})

describe('formatBytes and parseBytes - Round-Trip Conversion', () => {
  it('round-trip conversion is identity operation', () => {
    const sizes = [
      0, // 0 B
      512, // 512 B
      1024, // 1 KB
      1536, // 1.5 KB
      1048576, // 1 MB
      1610612736, // 1.5 GB
      5497558138880, // 5 TB
    ]

    sizes.forEach((bytes) => {
      const formatted = formatBytes(bytes)
      const parsed = parseBytes(formatted)
      expect(parsed).toBe(bytes)
    })
  })

  it('handles edge cases gracefully', () => {
    // formatBytes edge cases
    expect(formatBytes(null)).toBe('0 B')
    expect(formatBytes(undefined)).toBe('0 B')
    expect(formatBytes(0)).toBe('0 B')

    // parseBytes edge cases
    expect(parseBytes(null)).toBeUndefined()
    expect(parseBytes(undefined)).toBeUndefined()
    expect(parseBytes('invalid')).toBeUndefined()
    expect(parseBytes('123')).toBeUndefined() // missing unit
    expect(parseBytes('XYZ MB')).toBeUndefined() // invalid number
  })

  it('formats bytes correctly', () => {
    expect(formatBytes(1024)).toBe('1.00 KB')
    expect(formatBytes(1048576)).toBe('1.00 MB')
    expect(formatBytes(1073741824)).toBe('1.00 GB')
    expect(formatBytes(1536)).toBe('1.50 KB')
  })

  it('parses various formats', () => {
    expect(parseBytes('1.5 GB')).toBe(1610612736)
    expect(parseBytes('1.5GB')).toBe(1610612736) // no space
    expect(parseBytes('1,024 KB')).toBe(1048576) // with comma
    expect(parseBytes('512 B')).toBe(512)
  })

  it('parseBytes handles case insensitivity', () => {
    expect(parseBytes('1.5 gb')).toBe(1610612736)
    expect(parseBytes('1.5 GB')).toBe(1610612736)
    expect(parseBytes('1.5 Gb')).toBe(1610612736)
  })
})

describe('formatDurationSeconds', () => {
  it('formats large durations correctly', () => {
    expect(formatDurationSeconds(90)).toContain('1 min')
    expect(formatDurationSeconds(3661)).toContain('1 hour')
    expect(formatDurationSeconds(3661)).toContain('1 min') // should show both
    expect(formatDurationSeconds(7200)).toContain('2 hours')
    expect(formatDurationSeconds(86400)).toContain('1 day')
    expect(formatDurationSeconds(90000)).toContain('1 day')
    expect(formatDurationSeconds(90000)).toContain('1 hour')
  })

  it('handles zero and edge cases', () => {
    expect(formatDurationSeconds(0)).toBe('0 sec')
    expect(formatDurationSeconds(null)).toBe('0 sec')
    expect(formatDurationSeconds(undefined)).toBe('0 sec')
  })

  it('shows only top 2 units for readability', () => {
    // 1 day, 2 hours, 3 minutes, 4 seconds = 93784 seconds
    const result = formatDurationSeconds(93784)

    // Should show only first 2 units (day and hours)
    expect(result).toContain('1 day')
    expect(result).toContain('2 hours')
    expect(result).not.toContain('min') // should not show minutes
    expect(result).not.toContain('sec') // should not show seconds
  })

  it('shows seconds only if less than 2 units', () => {
    expect(formatDurationSeconds(5)).toBe('5 sec')
    expect(formatDurationSeconds(65)).toContain('1 min')
    expect(formatDurationSeconds(65)).toContain('5 sec')
  })

  it('handles single unit durations', () => {
    expect(formatDurationSeconds(30)).toBe('30 sec')
    expect(formatDurationSeconds(60)).toBe('1 min')
    expect(formatDurationSeconds(3600)).toBe('1 hour')
  })
})
