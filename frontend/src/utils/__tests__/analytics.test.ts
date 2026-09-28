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
      keepalive: false,
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
    expect(fetchMock().mock.calls[0][1].keepalive).toBe(true)
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })

  it('splits batches by size so no body passes 60 KB, and keepalive stays within 64 KB', async () => {
    const a = await load()
    for (let i = 0; i < 50; i++) a.trackEvent('Backup', 'Start', { note: 'x'.repeat(1500) })
    const bodies = fetchMock().mock.calls.map(([, init]) => (init as RequestInit).body as string)
    expect(bodies.length).toBeGreaterThan(1)
    for (const body of bodies)
      expect(new TextEncoder().encode(body).length).toBeLessThanOrEqual(60_000)
    expect(sent()).toHaveLength(50)

    fetchMock().mockClear()
    for (let i = 0; i < 49; i++) a.trackEvent('Backup', 'Start', { note: 'x'.repeat(1500) })
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    const kept = fetchMock()
      .mock.calls.filter(([, init]) => (init as RequestInit).keepalive)
      .reduce(
        (total, [, init]) =>
          total + new TextEncoder().encode((init as RequestInit).body as string).length,
        0
      )
    expect(kept).toBeLessThanOrEqual(60_000)
    expect(sent()).toHaveLength(49)
  })

  it('hashes any *_name prop so raw entity names cannot leak', async () => {
    const a = await load()
    a.trackEvent('Backup', 'Complete', { schedule_name: 'nightly-nas', name: 'de' })
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event.props.schedule_name).toBe(a.anonymizeEntityName('nightly-nas'))
    expect(event.props.name).toBe('de')
  })

  it('hashes path-like and user@host prop values, whatever the key', async () => {
    const a = await load()
    a.trackEvent('Navigation', 'Filter', {
      filter_kind: 'repository',
      filter_value: '/mnt/backups/nas',
      remote: 'ssh://borg@host:22/./repo',
      target: 'borg@host',
      status: 'failed',
    })
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event.props).toEqual({
      filter_kind: 'repository',
      filter_value: a.anonymizeEntityName('/mnt/backups/nas'),
      remote: a.anonymizeEntityName('ssh://borg@host:22/./repo'),
      target: a.anonymizeEntityName('borg@host'),
      status: 'failed',
    })
  })

  it('scrubs nested objects and arrays the same way', async () => {
    const a = await load()
    a.trackEvent('Backup', 'Start', {
      source: { repository_name: 'nas', path: '/srv/data', kind: 'local' },
      paths: ['/etc', 'relative'],
    })
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event.props).toEqual({
      source: {
        repository_name: a.anonymizeEntityName('nas'),
        path: a.anonymizeEntityName('/srv/data'),
        kind: 'local',
      },
      paths: [a.anonymizeEntityName('/etc'), 'relative'],
    })
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

  it('sends the first page view once preferences load, not before', async () => {
    vi.resetModules()
    prefs.value = { analytics_enabled: true, analytics_instance_key: KEY }
    localStorage.setItem('access_token', 'token')
    const a = await import('../analytics')
    a.trackPageView()
    await a.loadUserPreference()
    vi.advanceTimersByTime(5000)
    expect(sent().map((e) => e.name)).toEqual(['pageview'])
  })

  it('keeps the path and time of each page view made while preferences load', async () => {
    vi.resetModules()
    prefs.value = { analytics_enabled: true, analytics_instance_key: KEY }
    localStorage.setItem('access_token', 'token')
    const a = await import('../analytics')
    window.history.pushState({}, '', '/dashboard')
    a.trackPageView()
    const firstAt = new Date().toISOString()
    vi.advanceTimersByTime(1000)
    window.history.pushState({}, '', '/repositories')
    a.trackPageView()
    vi.advanceTimersByTime(1000)
    window.history.pushState({}, '', '/settings')
    await a.loadUserPreference()
    vi.advanceTimersByTime(5000)
    expect(sent().map((e) => [e.name, e.path])).toEqual([
      ['pageview', '/dashboard'],
      ['pageview', '/repositories'],
    ])
    expect(sent()[0].occurred_at).toBe(firstAt)
  })

  it('never replays a page view made while analytics was off after opting back in', async () => {
    const a = await load({ analytics_enabled: false })
    a.trackPageView()
    prefs.value = { ...prefs.value, analytics_enabled: true }
    await a.resetOptOutCache()
    vi.advanceTimersByTime(5000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('does not hold page views made while an off preference reloads', async () => {
    const a = await load({ analytics_enabled: false })
    prefs.value = { ...prefs.value, analytics_enabled: true }
    const reloading = a.resetOptOutCache()
    a.trackPageView()
    await reloading
    vi.advanceTimersByTime(5000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('keeps the consent answer when preferences failed to load, and sends it once they do', async () => {
    vi.resetModules()
    prefs.value = { analytics_enabled: true, analytics_instance_key: KEY }
    localStorage.setItem('access_token', 'token')
    const req = await import('../../services/authRequest')
    vi.mocked(req.fetchJsonForAuthMode).mockRejectedValueOnce(new Error('offline'))
    const a = await import('../analytics')
    await a.loadUserPreference()
    a.trackConsentResponse(true)
    expect(globalThis.fetch).not.toHaveBeenCalled()
    await a.resetOptOutCache()
    expect(sent().map((e) => e.name)).toEqual(['Consent - Accept'])
  })

  it('drops the early page view when preferences say analytics is off', async () => {
    vi.resetModules()
    prefs.value = { analytics_enabled: false, analytics_instance_key: KEY }
    localStorage.setItem('access_token', 'token')
    const a = await import('../analytics')
    a.trackPageView()
    await a.loadUserPreference()
    vi.advanceTimersByTime(5000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('on opt-out sends only the opt-out event and nothing queued or tracked after it', async () => {
    const a = await load()
    a.trackEvent('Backup', 'Start')
    a.trackOptOut()
    a.trackEvent('Settings', 'Edit')
    a.trackPageView()
    vi.advanceTimersByTime(5000)
    expect(sent().map((e) => e.name)).toEqual(['Settings - OptOut'])
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
