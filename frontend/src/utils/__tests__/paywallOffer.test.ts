import { afterEach, describe, expect, it } from 'vitest'
import {
  fullAccessEndedRecently,
  noteFullAccessEnd,
  offerTrigger,
  paywallIntentDays,
  recordPaywallIntent,
  storeOffer,
} from '../paywallOffer'

const DAY = 86_400_000

describe('paywall offer triggers', () => {
  afterEach(() => localStorage.clear())

  it('counts days, not cards, and offers on the third day', () => {
    const start = Date.parse('2026-11-01T10:00:00Z')
    recordPaywallIntent(new Date(start))
    recordPaywallIntent(new Date(start + 1000))
    recordPaywallIntent(new Date(start + DAY))
    expect(paywallIntentDays()).toBe(2)
    expect(offerTrigger()).toBeNull()
    recordPaywallIntent(new Date(start + 5 * DAY))
    expect(offerTrigger()).toBe('repeat')
  })

  it('offers on the end of full access only for 14 days, and only if it saw it running', () => {
    expect(fullAccessEndedRecently()).toBe(false)
    noteFullAccessEnd(new Date(Date.now() - 3 * DAY).toISOString())
    expect(offerTrigger()).toBe('expired')
    noteFullAccessEnd(new Date(Date.now() - 15 * DAY).toISOString())
    expect(offerTrigger()).toBeNull()
    noteFullAccessEnd(new Date(Date.now() + DAY).toISOString())
    expect(fullAccessEndedRecently()).toBe(false)
  })

  it('never offers again once claimed or refused', () => {
    for (let i = 0; i < 3; i += 1) recordPaywallIntent(new Date(Date.now() - i * DAY))
    storeOffer({ denied: 'offer_already_used' })
    expect(offerTrigger()).toBeNull()
    storeOffer({ offer_id: 'ofr_1', expires_at: '2020-01-01T00:00:00Z' })
    expect(offerTrigger()).toBeNull()
  })
})
