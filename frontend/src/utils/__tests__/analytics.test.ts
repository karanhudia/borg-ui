import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../services/api', () => ({
  authAPI: {
    getAuthConfig: vi.fn(async () => ({
      data: { proxy_auth_enabled: false, insecure_no_auth_enabled: false },
    })),
  },
}))
const prefs = vi.hoisted(() => ({ value: {} as Record<string, unknown> }))
vi.mock('../../services/authRequest', () => ({
  fetchJsonForAuthMode: vi.fn(async () => ({ json: async () => ({ preferences: prefs.value }) })),
}))

const KEY = 'a'.repeat(64)
const USER = 'b'.repeat(64)

async function load(over: Record<string, unknown> = {}) {
  vi.resetModules()
  prefs.value = {
    analytics_enabled: true,
    analytics_consent_given: true,
    analytics_instance_key: KEY,
    analytics_user_key: USER,
    ...over,
  }
  localStorage.setItem('access_token', 'token')
  const mod = await import('../analytics')
  await mod.loadUserPreference()
  return mod
}

const fetchMock = () => globalThis.fetch as unknown as ReturnType<typeof vi.fn>
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const sent = (): any[] =>
  fetchMock().mock.calls.flatMap(
    ([, init]) => JSON.parse((init as RequestInit).body as string).events
  )

beforeEach(() => {
  vi.useFakeTimers()
  globalThis.fetch = vi.fn(
    async () => new Response(null, { status: 204 })
  ) as unknown as typeof fetch
  window.history.pushState({}, '', '/repositories?secret=1#x')
})
afterEach(() => {
  vi.useRealTimers()
  localStorage.clear()
})

describe('analytics transport', () => {
  it('batches events and posts them without referrer or credentials', async () => {
    const a = await load()
    a.setAppVersion('2.3.0')
    a.setAnalyticsPlan('community')
    a.trackEvent('Plan', 'FeatureBlocked', { feature: 'rclone' })
    a.trackPageView()
    expect(globalThis.fetch).not.toHaveBeenCalled()

    vi.advanceTimersByTime(5000)

    const [url, init] = fetchMock().mock.calls[0]
    expect(url).toBe(a.ANALYTICS_ENDPOINT)
    expect(init).toMatchObject({
      method: 'POST',
      keepalive: true,
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
    })
    expect(init.headers).toEqual({ 'Content-Type': 'text/plain' })
    const [event, pageview] = sent()
    expect(event).toMatchObject({
      source: 'app',
      name: 'Plan - FeatureBlocked',
      instance_key: KEY,
      user_key: USER,
      path: '/repositories',
      app_version: '2.3.0',
      plan: 'community',
      props: { feature: 'rclone' },
    })
    expect(event.event_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    )
    expect(pageview.name).toBe('pageview')
  })

  it('never sends the query string, hash or host', async () => {
    const a = await load()
    a.trackPageView('/repositories?secret=1')
    vi.advanceTimersByTime(5000)
    const body = JSON.stringify(sent())
    expect(body).not.toContain('secret')
    expect(body).not.toContain(window.location.host)
  })

  it('flushes immediately once the tab is hidden', async () => {
    const a = await load()
    a.trackEvent('Backup', 'Start')
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(sent()).toHaveLength(1)
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })

  it('hashes any *_name prop so raw entity names cannot leak', async () => {
    const a = await load()
    a.trackEvent('Backup', 'Complete', { schedule_name: 'nightly-nas', name: 'de' })
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event.props.schedule_name).toBe(a.anonymizeEntityName('nightly-nas'))
    expect(event.props.name).toBe('de')
  })
})

describe('analytics gating', () => {
  it('sends nothing when analytics is off', async () => {
    const a = await load({ analytics_enabled: false })
    a.trackEvent('Backup', 'Start')
    a.trackPageView()
    vi.advanceTimersByTime(5000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
    expect(a.getAnalyticsInstanceKey()).toBeNull()
  })

  it('still sends the one-shot consent and opt-out events, immediately', async () => {
    const a = await load({ analytics_enabled: false })
    a.trackConsentResponse(false)
    a.trackOptOut()
    expect(sent().map((e) => e.name)).toEqual(['Consent - Decline', 'Settings - OptOut'])
  })

  it('sends nothing before preferences load', async () => {
    vi.resetModules()
    const a = await import('../analytics')
    a.trackEvent('Backup', 'Start')
    vi.advanceTimersByTime(5000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('exposes the instance key only while analytics is on', async () => {
    const a = await load()
    expect(a.getAnalyticsInstanceKey()).toBe(KEY)
  })

  it('swallows transport failures', async () => {
    const a = await load()
    globalThis.fetch = vi.fn(async () => {
      throw new Error('offline')
    }) as unknown as typeof fetch
    a.trackEvent('Backup', 'Start')
    expect(() => vi.advanceTimersByTime(5000)).not.toThrow()
  })
})

describe('anonymizeEntityName', () => {
  it('is a stable 8-hex hash', async () => {
    const a = await load()
    expect(a.anonymizeEntityName('repo')).toMatch(/^[0-9a-f]{8}$/)
    expect(a.anonymizeEntityName('repo')).toBe(a.anonymizeEntityName('repo'))
  })
})
