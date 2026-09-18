import { describe, expect, it } from 'vitest'
import { formatRetention, sameRetention } from '../formatRetention'

describe('formatRetention', () => {
  it('lists the non-zero keep rules in period order', () => {
    expect(
      formatRetention({
        keep_hourly: 0,
        keep_daily: 7,
        keep_weekly: 4,
        keep_monthly: 6,
        keep_quarterly: 0,
        keep_yearly: 1,
        keep_within: '',
      })
    ).toBe('7d 4w 6m 1y')
  })
  it('puts keep_within first and skips a null policy', () => {
    expect(
      formatRetention({
        keep_hourly: 2,
        keep_daily: 0,
        keep_weekly: 0,
        keep_monthly: 12,
        keep_quarterly: 1,
        keep_yearly: 3,
        keep_within: '2d',
      })
    ).toBe('within 2d 2h 12m 1q 3y')
    expect(formatRetention(null)).toBe('')
  })
})

describe('sameRetention', () => {
  it('ignores key order and treats an empty keep_within as null', () => {
    const stored = {
      keep_hourly: 0,
      keep_daily: 7,
      keep_weekly: 4,
      keep_monthly: 6,
      keep_quarterly: 0,
      keep_yearly: 1,
      keep_within: null,
    }
    const form = {
      keep_within: '',
      keep_hourly: 0,
      keep_daily: 7,
      keep_weekly: 4,
      keep_monthly: 6,
      keep_quarterly: 0,
      keep_yearly: 1,
    }
    expect(sameRetention(stored, form)).toBe(true)
    expect(sameRetention(stored, { ...form, keep_daily: 8 })).toBe(false)
    expect(sameRetention(stored, { ...form, keep_within: '2d' })).toBe(false)
    expect(sameRetention(null, form)).toBe(false)
  })
})
