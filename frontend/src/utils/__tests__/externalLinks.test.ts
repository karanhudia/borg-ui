import { describe, expect, it, vi } from 'vitest'

const key = vi.hoisted(() => ({ value: null as string | null }))
vi.mock('../analytics', () => ({ getAnalyticsInstanceKey: () => key.value }))

import { buildBuyUrl, refreshBuyLink } from '../externalLinks'

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

describe('buy link activation', () => {
  it('adds the identity that became eligible after rendering', () => {
    key.value = null
    const anchor = document.createElement('a')
    anchor.href = buildBuyUrl({ plan: 'pro', src: 'app-expired', offer: 'expired' })
    key.value = 'a'.repeat(64)
    refreshBuyLink({ currentTarget: anchor })
    const url = new URL(anchor.href)
    expect(url.searchParams.get('ik')).toBe('a'.repeat(64))
    expect(url.searchParams.get('plan')).toBe('pro')
    expect(url.searchParams.get('src')).toBe('app-expired')
    expect(url.searchParams.get('offer')).toBe('expired')
  })

  it('removes a stale identity when analytics was turned off after rendering', () => {
    key.value = 'a'.repeat(64)
    const anchor = document.createElement('a')
    anchor.href = buildBuyUrl({ src: 'app-drawer' })
    key.value = null
    refreshBuyLink({ currentTarget: anchor })
    expect(new URL(anchor.href).searchParams.has('ik')).toBe(false)
  })

  it.each(['bad', '', 'a'.repeat(63)])('does not attach malformed identity %j', (value) => {
    key.value = value
    expect(new URL(buildBuyUrl({ src: 'app-drawer' })).searchParams.has('ik')).toBe(false)
  })
})
