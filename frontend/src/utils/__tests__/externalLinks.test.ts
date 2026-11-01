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
    anchor.href = buildBuyUrl({ plan: 'pro', src: 'app-expired' })
    key.value = 'a'.repeat(64)
    refreshBuyLink({ currentTarget: anchor })
    const url = new URL(anchor.href)
    expect(url.searchParams.get('ik')).toBe('a'.repeat(64))
    expect(url.searchParams.get('plan')).toBe('pro')
    expect(url.searchParams.get('src')).toBe('app-expired')
    expect(url.searchParams.get('offer')).toBeNull()
  })

  it('carries a claimed offer that was claimed after rendering, until it lapses', () => {
    const anchor = document.createElement('a')
    anchor.href = buildBuyUrl({ plan: 'pro', src: 'app-gate-rclone' })
    const expires = new Date(Date.now() + 86_400_000).toISOString()
    localStorage.setItem(
      'borgui.paywallOffer',
      JSON.stringify({ offer_id: 'ofr_1', percent: 5, expires_at: expires })
    )
    refreshBuyLink({ currentTarget: anchor })
    expect(new URL(anchor.href).searchParams.get('offer')).toBe('ofr_1')
    localStorage.setItem(
      'borgui.paywallOffer',
      JSON.stringify({ offer_id: 'ofr_1', expires_at: '2020-01-01T00:00:00Z' })
    )
    refreshBuyLink({ currentTarget: anchor })
    expect(new URL(anchor.href).searchParams.get('offer')).toBeNull()
    localStorage.removeItem('borgui.paywallOffer')
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
