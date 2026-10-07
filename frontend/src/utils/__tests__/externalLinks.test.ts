import { describe, expect, it, vi } from 'vitest'

const key = vi.hoisted(() => ({ value: null as string | null }))
vi.mock('../analytics', () => ({ getAnalyticsInstanceKey: () => key.value }))

import { buildBuyUrl } from '../externalLinks'

describe('buildBuyUrl', () => {
  it('adds the instance key when analytics is on', () => {
    key.value = 'a'.repeat(64)
    const url = new URL(buildBuyUrl({ plan: 'pro', src: 'app-licensing' }))
    expect(url.searchParams.get('ik')).toBe('a'.repeat(64))
    expect(url.searchParams.get('src')).toBe('app-licensing')
    expect(url.searchParams.get('plan')).toBe('pro')
  })

  it('omits it when analytics is off', () => {
    key.value = null
    expect(new URL(buildBuyUrl({ src: 'app-upgrade-prompt' })).searchParams.has('ik')).toBe(false)
  })
})
