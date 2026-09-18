import { describe, expect, it } from 'vitest'
import { formatRetention } from '../formatRetention'

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
