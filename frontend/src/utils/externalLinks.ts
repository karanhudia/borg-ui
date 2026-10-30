import { getAnalyticsInstanceKey } from './analytics'
import { liveOfferId } from './paywallOffer'

export const BUY_URL = 'https://borgui.com/buy'

export type BuyLinkContext = {
  plan?: 'pro' | 'enterprise'
  src: string
}

/** Buy link with the context the storefront uses to prefill, scroll, and apply offers. */
export function buildBuyUrl({ plan, src }: BuyLinkContext): string {
  const params = new URLSearchParams()
  if (plan) params.set('plan', plan)
  params.set('src', src)
  // A one-time offer this install claimed rides on every buy link until it lapses.
  const offer = liveOfferId()
  if (offer) params.set('offer', offer)
  // Joins the storefront visit to this install's usage; absent when analytics is off.
  const ik = getAnalyticsInstanceKey()
  if (ik && /^[a-f0-9]{64}$/.test(ik)) params.set('ik', ik)
  return `${BUY_URL}?${params.toString()}`
}

/** Refresh synchronously so ordinary, keyboard and new-tab activation use current consent. */
export function refreshBuyLink({ currentTarget }: { currentTarget: HTMLAnchorElement }): void {
  const url = new URL(currentTarget.href)
  if (url.origin !== new URL(BUY_URL).origin || url.pathname !== '/buy') return
  url.searchParams.delete('ik')
  url.searchParams.delete('offer')
  const offer = liveOfferId()
  if (offer) url.searchParams.set('offer', offer)
  const ik = getAnalyticsInstanceKey()
  if (ik && /^[a-f0-9]{64}$/.test(ik)) url.searchParams.set('ik', ik)
  currentTarget.href = url.toString()
}
