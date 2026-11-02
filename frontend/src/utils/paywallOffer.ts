/**
 * The one-time paywall offer, as this browser remembers it.
 *
 * The app only decides whether to show "claim 5% off" inside a card the user
 * opened; the activation service decides whether the offer is issued, once
 * per install. So none of this is a security boundary.
 * ponytail: per browser, so a second browser counts intent from zero and a
 * cleared one forgets a claim (the service still returns the same offer).
 * Move to the app database if that ever matters.
 */

const INTENT_KEY = 'borgui.paywallIntentDays'
const OFFER_KEY = 'borgui.paywallOffer'
const ACCESS_END_KEY = 'borgui.fullAccessEndsAt'

/** Mirrors the service: intent on this many different days earns the offer. */
export const MIN_INTENT_DAYS = 3
/** And for this long after full access ends, the end itself does. */
export const EXPIRED_TRIGGER_DAYS = 14
const DAY_MS = 24 * 60 * 60 * 1000

export interface StoredOffer {
  offer_id?: string
  percent?: number
  expires_at?: string
  /** The service said no; the card stops offering it. */
  denied?: string
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Private mode or storage full: the offer simply is not shown.
  }
}

/** A real upgrade card was shown because the user opened it, clicked a lock or
 *  had an action refused. Counted per day, not per card. */
export function recordPaywallIntent(now = new Date()) {
  const day = now.toISOString().slice(0, 10)
  const days = read<string[]>(INTENT_KEY, [])
  if (!days.includes(day)) write(INTENT_KEY, [...days, day].slice(-30))
}

export function paywallIntentDays(): number {
  return read<string[]>(INTENT_KEY, []).length
}

/** Noted while full access runs, because once it ends the app no longer
 *  knows when it did. Installs that expired before this release never see
 *  the expired trigger, which is the point: it is for the days right after. */
export function noteFullAccessEnd(expiresAt: string | null | undefined) {
  if (expiresAt) write(ACCESS_END_KEY, expiresAt)
}

export function fullAccessEndedRecently(now = Date.now()): boolean {
  const ends = Date.parse(read<string>(ACCESS_END_KEY, ''))
  return Number.isFinite(ends) && ends <= now && now - ends < EXPIRED_TRIGGER_DAYS * DAY_MS
}

export function storedOffer(): StoredOffer {
  return read<StoredOffer>(OFFER_KEY, {})
}

export function storeOffer(offer: StoredOffer) {
  write(OFFER_KEY, offer)
}

/** The claimed offer id while it is still good, for the buy links. */
export function liveOfferId(now = Date.now()): string | null {
  const offer = storedOffer()
  if (!offer.offer_id || !offer.expires_at) return null
  return Date.parse(offer.expires_at) > now ? offer.offer_id : null
}

/** Which trigger a claim would use right now, or null when the card should not offer one. */
export function offerTrigger(): 'repeat' | 'expired' | null {
  const offer = storedOffer()
  if (offer.denied || offer.offer_id) return null
  if (paywallIntentDays() >= MIN_INTENT_DAYS) return 'repeat'
  if (fullAccessEndedRecently()) return 'expired'
  return null
}
