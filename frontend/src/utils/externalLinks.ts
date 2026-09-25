import { getAnalyticsInstanceKey } from './analytics'

export const BUY_URL = 'https://borgui.com/buy'

export type BuyLinkContext = {
  plan?: 'pro' | 'enterprise'
  src: string
  offer?: 'expired'
}

/** Buy link with the context the storefront uses to prefill, scroll, and apply offers. */
export function buildBuyUrl({ plan, src, offer }: BuyLinkContext): string {
  const params = new URLSearchParams()
  if (plan) params.set('plan', plan)
  params.set('src', src)
  if (offer) params.set('offer', offer)
  // Joins the storefront visit to this install's usage; absent when analytics is off.
  const ik = getAnalyticsInstanceKey()
  if (ik) params.set('ik', ik)
  return `${BUY_URL}?${params.toString()}`
}
