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
  vi.unstubAllEnvs()
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

  it('counts keepalive bytes across overlapping flushes until each send settles', async () => {
    const a = await load()
    const hide = () => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    }
    for (let i = 0; i < 30; i++) a.trackEvent('Backup', 'Start', { note: 'x'.repeat(1500) })
    hide()
    for (let i = 0; i < 30; i++) a.trackEvent('Backup', 'Start', { note: 'x'.repeat(1500) })
    hide()
    const kept = fetchMock()
      .mock.calls.filter(([, init]) => (init as RequestInit).keepalive)
      .reduce(
        (total, [, init]) =>
          total + new TextEncoder().encode((init as RequestInit).body as string).length,
        0
      )
    expect(kept).toBeLessThanOrEqual(60_000)
    expect(sent()).toHaveLength(60)

    // Once those settle, the budget is free again.
    await vi.runAllTimersAsync()
    fetchMock().mockClear()
    a.trackEvent('Backup', 'Start')
    hide()
    expect(fetchMock().mock.calls[0][1].keepalive).toBe(true)
  })

  it('replaces props the ingest would reject as too large, keeping the event', async () => {
    const a = await load()
    a.trackEvent('Backup', 'Fail', { error: 'x'.repeat(100_000), code: 5 })
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event.name).toBe('Backup - Fail')
    expect(event.props).toEqual({ props_truncated: true })
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

describe('route normalization', () => {
  it('replaces ids in the path of page views and events with placeholders', async () => {
    const a = await load()
    window.history.pushState({}, '', '/archives/12/345')
    a.trackPageView()
    window.history.pushState({}, '', '/repositories/7/prune-preview')
    a.trackEvent('Archive', 'View')
    vi.advanceTimersByTime(5000)
    expect(sent().map((event) => event.path)).toEqual([
      '/archives/:id/:id',
      '/repositories/:id/prune-preview',
    ])
  })

  it('keeps static routes as they are', async () => {
    const a = await load()
    expect(a.normalizeRoute('/settings/beta')).toBe('/settings/beta')
    expect(a.normalizeRoute('/schedule/checks')).toBe('/schedule/checks')
    expect(a.normalizeRoute('/archives/aid:abc123/9')).toBe('/archives/:id/:id')
    // Route params are ids even when they happen to look like words.
    expect(a.normalizeRoute('/archives/photos/nightly')).toBe('/archives/:id/:id')
    expect(a.normalizeRoute('/repositories/photos/prune-preview')).toBe(
      '/repositories/:id/prune-preview'
    )
    expect(a.normalizeRoute('/repositories/photos')).toBe('/repositories/:id')
    expect(a.normalizeRoute('/repositories')).toBe('/repositories')
    expect(a.normalizeRoute('/')).toBe('/')
    // Anything outside the app's routes could be a name in a typed URL.
    expect(a.normalizeRoute('/alice')).toBe('/:other')
    expect(a.normalizeRoute('/alice/docs')).toBe('/:other')
    expect(a.normalizeRoute('/settings/account/alice')).toBe('/settings/account/:id')
    expect(a.normalizeRoute('/settings/alice')).toBe('/settings/:id')
    expect(a.normalizeRoute('/schedule/checks')).toBe('/schedule/checks')
    expect(a.normalizeRoute('/schedule/alice')).toBe('/schedule/:id')
    expect(a.normalizeRoute('/dashboard/alice')).toBe('/dashboard/:id')
    // After a route's ids only its own fixed words survive.
    expect(a.normalizeRoute('/archives/photos/nightly/alice')).toBe('/archives/:id/:id/:id')
    expect(a.normalizeRoute('/repositories/7/alice')).toBe('/repositories/:id/:id')
  })

  it('drops the deployment base path', async () => {
    ;(window as unknown as { __BASE_PATH__?: string }).__BASE_PATH__ = '/acme-backups'
    try {
      const a = await load()
      window.history.pushState({}, '', '/acme-backups/repositories')
      a.trackPageView()
      vi.advanceTimersByTime(5000)
      expect(sent()[0].path).toBe('/repositories')
    } finally {
      delete (window as unknown as { __BASE_PATH__?: string }).__BASE_PATH__
    }
  })
})

describe('KNOWN_ROUTE_ROOTS', () => {
  it('covers every top-level route in App.tsx', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const app = readFileSync(resolve(__dirname, '../../App.tsx'), 'utf8')
    const roots = [...app.matchAll(/path="\/([a-z-]+)/g)].map((match) => match[1])
    expect(roots.length).toBeGreaterThan(10)
    const a = await load()
    expect(roots.filter((root) => !a.KNOWN_ROUTE_ROOTS.has(root))).toEqual([])
  })
})

describe('ROUTE_WORDS', () => {
  it('matches the Settings tabs and Schedule views the pages define', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const read = (file: string) => readFileSync(resolve(__dirname, '..', '..', file), 'utf8')
    const settings = read('pages/Settings.tsx')
    const tabBlock = settings.slice(
      settings.indexOf('const getTabOrder'),
      settings.indexOf('}, [', settings.indexOf('const getTabOrder'))
    )
    const tabs = [...tabBlock.matchAll(/'([a-z-]+)'/g)].map((match) => match[1])
    const views = [...read('pages/Schedule.tsx').matchAll(/'\/schedule\/([a-z-]+)'/g)].map(
      (match) => match[1]
    )
    expect(tabs.length).toBeGreaterThan(10)
    expect(views.length).toBeGreaterThan(3)
    const a = await load()
    expect([...new Set(tabs)].sort()).toEqual([...a.ROUTE_WORDS.settings].sort())
    expect([...new Set(views)].sort()).toEqual([...a.ROUTE_WORDS.schedule].sort())
  })
})

describe('errorClass', () => {
  it('maps an error to a coarse class, never its message', async () => {
    const a = await load()
    const http = (status: number) => ({ isAxiosError: true, response: { status } })
    expect(a.errorClass(http(400))).toBe('validation')
    expect(a.errorClass(http(422))).toBe('validation')
    expect(a.errorClass(http(401))).toBe('auth')
    expect(a.errorClass(http(403))).toBe('permission')
    expect(a.errorClass(http(404))).toBe('not_found')
    expect(a.errorClass(http(409))).toBe('conflict')
    expect(a.errorClass(http(429))).toBe('rate_limited')
    expect(a.errorClass(http(502))).toBe('server')
    expect(a.errorClass(http(418))).toBe('client')
    expect(a.errorClass({ isAxiosError: true, code: 'ECONNABORTED' })).toBe('timeout')
    expect(a.errorClass({ isAxiosError: true, code: 'ERR_NETWORK' })).toBe('network')
    expect(a.errorClass(new Error('/srv/secret failed'))).toBe('unknown')
  })
})

describe('testResult', () => {
  it('gives every failed test a class, check_failed when the request itself worked', async () => {
    const a = await load()
    expect(a.testResult(true)).toEqual({ success: true })
    expect(a.testResult(false)).toEqual({ success: false, error_class: 'check_failed' })
    expect(a.testResult(false, { isAxiosError: true, code: 'ECONNABORTED' })).toEqual({
      success: false,
      error_class: 'timeout',
    })
  })
})

describe('trackApiError', () => {
  const planError = {
    isAxiosError: true,
    config: { method: 'post', url: '/v2/repositories/' },
    response: {
      status: 403,
      data: {
        detail: {
          key: 'backend.errors.plan.featureNotAvailable',
          feature: 'borg_v2',
          required: 'pro',
          current: 'community',
        },
      },
    },
  }

  it('reports a plan gate refused by the backend as a blocked feature', async () => {
    const a = await load()
    a.trackApiError(planError)
    vi.advanceTimersByTime(5000)
    expect(sent()[0]).toMatchObject({
      name: 'Plan - FeatureBlocked',
      props: {
        feature: 'borg_v2',
        required_plan: 'pro',
        current_plan: 'community',
        allowed: false,
        surface: 'api',
        operation: 'repositories',
        gate_mode: 'api_error',
      },
    })
  })

  it('recognises a plan refusal sent as a plain or JSON string detail', async () => {
    const a = await load()
    const refuse = (detail: unknown) =>
      a.trackApiError({
        isAxiosError: true,
        config: { method: 'post', url: '/repositories/' },
        response: { status: 403, data: { detail } },
      })
    refuse('backend.errors.plan.featureNotAvailable')
    refuse(JSON.stringify({ key: 'backend.errors.plan.featureNotAvailable', feature: 'rclone' }))
    refuse('{not json')
    vi.advanceTimersByTime(5000)
    expect(
      sent()
        .filter((event) => event.name !== 'Error - Report')
        .map((event) => [event.name, event.props.feature])
    ).toEqual([
      ['Plan - FeatureBlocked', 'unknown'],
      ['Plan - FeatureBlocked', 'rclone'],
      ['API - Fail', undefined],
    ])
  })

  it('reports a failed change without raw error details', async () => {
    const a = await load()
    a.trackApiError({
      isAxiosError: true,
      config: { method: 'put', url: '/repositories/12/settings?name=home' },
      response: { status: 500, data: { detail: 'borg: /srv/secret is locked' } },
    })
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event).toMatchObject({
      name: 'API - Fail',
      props: { area: 'repositories', method: 'put', status: 500, error_class: 'server' },
    })
    expect(JSON.stringify(event)).not.toContain('secret')
  })

  it.each([400, 500])(
    'retains a structured repository failure reason for HTTP %s',
    async (status) => {
      const a = await load()
      a.trackApiError({
        isAxiosError: true,
        config: { method: 'post', url: '/repositories/' },
        response: {
          status,
          data: {
            detail: {
              key: 'backend.errors.repo.failedToInitializeRepository',
              params: { error: 'private repository details' },
            },
          },
        },
      })
      vi.advanceTimersByTime(5000)
      const event = sent().find((event) => event.name === 'API - Fail')
      expect(event.props.error_key).toBe('repo.failedToInitializeRepository')
      expect(JSON.stringify(event)).not.toContain('private repository details')
    }
  )

  it.each([
    'private details',
    'backend.errors.repo.private/path',
    'backend.errors.repo.failedToInitializeRepository\n',
    'backend.errors.' + 'x'.repeat(200),
    42,
  ])('omits a non-machine-readable reason key (%s)', async (key) => {
    const a = await load()
    a.trackApiError({
      isAxiosError: true,
      config: { method: 'post', url: '/repositories/' },
      response: { status: 500, data: { detail: { key } } },
    })
    vi.advanceTimersByTime(5000)
    expect(sent().find((event) => event.name === 'API - Fail').props).not.toHaveProperty(
      'error_key'
    )
  })

  it('skips a base path in an absolute URL and gives up without an api prefix', async () => {
    const a = await load()
    const fail = (url: string) =>
      a.trackApiError({
        isAxiosError: true,
        config: { method: 'post', url },
        response: { status: 500 },
      })
    fail('https://nas.local/acme-backups/api/v2/archives/3')
    fail('https://nas.local/acme-backups/repositories')
    vi.advanceTimersByTime(5000)
    expect(sent().map((event) => event.props.area)).toEqual(['archives', 'other'])
  })

  it('takes the area from an absolute request URL', async () => {
    const a = await load()
    a.trackApiError({
      isAxiosError: true,
      config: { method: 'post', url: 'https://nas.local/api/backup-plans/3/run' },
      response: { status: 409 },
    })
    vi.advanceTimersByTime(5000)
    expect(sent().find((event) => event.name === 'API - Fail').props).toMatchObject({
      area: 'backup-plans',
      error_class: 'conflict',
    })
  })

  it('ignores reads and expired sessions', async () => {
    const a = await load()
    a.trackApiError({
      isAxiosError: true,
      config: { method: 'get', url: '/x' },
      response: { status: 500 },
    })
    a.trackApiError({
      isAxiosError: true,
      config: { method: 'post', url: '/x' },
      response: { status: 401 },
    })
    vi.advanceTimersByTime(5000)
    expect(sent().filter((event) => event.name === 'API - Fail')).toEqual([])
    const reports = sent().filter((event) => event.name === 'Error - Report')
    expect(reports).toHaveLength(1)
    expect(reports[0].props).toMatchObject({ kind: 'api', method: 'post', status: 401 })
  })
})

describe('enqueueErrorReport', () => {
  const report = { origin: 'frontend', kind: 'uncaught', message: 'boom' }

  it('sends without a key when none is known, and not after a no', async () => {
    const a = await load({ analytics_instance_key: null, analytics_user_key: null })
    a.enqueueErrorReport(report)
    vi.advanceTimersByTime(5000)
    const [event] = sent()
    expect(event).toMatchObject({ name: 'Error - Report', source: 'app', props: report })
    expect(event).not.toHaveProperty('instance_key')

    fetchMock().mockClear()
    const off = await load({ analytics_enabled: false })
    off.enqueueErrorReport(report)
    vi.advanceTimersByTime(10_000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('sends with the key when known, and leaves paths and user@host in props alone', async () => {
    const a = await load()
    a.enqueueErrorReport({ ...report, message: '/a/b user@host' })
    vi.advanceTimersByTime(5000)
    expect(sent()[0]).toMatchObject({
      instance_key: KEY,
      props: { message: '/a/b user@host' },
    })
  })

  it('holds reports until the first load settles, at most 20, then sends them', async () => {
    vi.resetModules()
    prefs.value = { analytics_enabled: true, analytics_instance_key: KEY }
    const a = await import('../analytics')
    for (let i = 0; i < 25; i++) a.enqueueErrorReport({ ...report, i })
    vi.advanceTimersByTime(4000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
    localStorage.setItem('access_token', 'token')
    await a.loadUserPreference()
    vi.advanceTimersByTime(5000)
    expect(sent()).toHaveLength(20)
    expect(sent()[0]).toMatchObject({ instance_key: KEY })
  })

  it('stops waiting for the preference after 5 seconds', async () => {
    vi.resetModules()
    const a = await import('../analytics')
    a.enqueueErrorReport(report)
    vi.advanceTimersByTime(5000)
    vi.advanceTimersByTime(5000)
    expect(sent()).toHaveLength(1)
    expect(sent()[0]).not.toHaveProperty('instance_key')
  })

  it('drops held reports at once on a decline, before any preference reload', async () => {
    vi.resetModules()
    const a = await import('../analytics')
    a.enqueueErrorReport(report)
    a.trackConsentResponse(false)
    vi.advanceTimersByTime(10_000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('drops reports already queued when the user declines', async () => {
    const a = await load()
    a.enqueueErrorReport(report)
    a.trackConsentResponse(false)
    expect(sent().map((e: { name: string }) => e.name)).toEqual(['Consent - Decline'])
  })

  it('drops held reports when the preference loads with a no', async () => {
    vi.resetModules()
    prefs.value = { analytics_enabled: false, analytics_instance_key: KEY }
    localStorage.setItem('access_token', 'token')
    const a = await import('../analytics')
    a.enqueueErrorReport(report)
    await a.loadUserPreference()
    vi.advanceTimersByTime(10_000)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })
})

describe('analytics startup integrity', () => {
  it('uses the build version before runtime system info arrives', async () => {
    vi.stubEnv('VITE_APP_VERSION', '2.4.1')
    const a = await load()
    a.trackPageView()
    a.flushAnalytics()
    expect(sent()[0].app_version).toBe('2.4.1')
  })

  it('enriches queued page views and early errors when the runtime version arrives', async () => {
    const a = await load()
    a.trackPageView()
    a.enqueueErrorReport({ message: 'early failure' })
    a.setAppVersion('2.4.2')
    a.flushAnalytics()
    expect(sent()).toHaveLength(2)
    expect(sent().every((event) => event.app_version === '2.4.2')).toBe(true)
  })

  it('does not overwrite a version already known when the event happened', async () => {
    const a = await load()
    a.setAppVersion('2.4.1')
    a.trackPageView()
    a.setAppVersion('2.4.2')
    a.flushAnalytics()
    expect(sent()[0].app_version).toBe('2.4.1')
  })

  it.each([undefined, '', 'bad', 123, {}])(
    'rejects malformed or absent identity %j',
    async (key) => {
      const a = await load({ analytics_instance_key: key })
      expect(a.getAnalyticsInstanceKey()).toBeNull()
      a.trackPageView()
      a.flushAnalytics()
      expect(sent()).toHaveLength(0)
    }
  )
})

describe('analytics retry integrity', () => {
  it.each(['network', 'server', 'rate-limit'])(
    'retries %s failures with the same event id and a bounded attempt count',
    async (failure) => {
      const a = await load()
      globalThis.fetch = vi.fn(async () => {
        if (failure === 'network') throw new TypeError('offline')
        return new Response(null, { status: failure === 'server' ? 503 : 429 })
      }) as unknown as typeof fetch
      a.trackPageView()
      a.flushAnalytics()
      await vi.runAllTimersAsync()
      expect(sent()).toHaveLength(3)
      expect(new Set(sent().map((event) => event.event_id)).size).toBe(1)
    }
  )

  it('does not retry a permanently rejected payload', async () => {
    const a = await load()
    globalThis.fetch = vi.fn(
      async () => new Response(null, { status: 400 })
    ) as unknown as typeof fetch
    a.trackPageView()
    a.flushAnalytics()
    await vi.runAllTimersAsync()
    expect(sent()).toHaveLength(1)
  })

  it('withdraws pending retries immediately on opt-out', async () => {
    const a = await load()
    globalThis.fetch = vi.fn(
      async () => new Response(null, { status: 503 })
    ) as unknown as typeof fetch
    a.trackPageView()
    a.flushAnalytics()
    await vi.advanceTimersByTimeAsync(0)
    a.trackOptOut()
    await vi.runAllTimersAsync()
    expect(sent().filter((event) => event.name === 'pageview')).toHaveLength(1)
  })

  it('does not revive an in-flight failure after preferences switch off', async () => {
    const a = await load()
    let fail!: (value: Response) => void
    globalThis.fetch = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          fail = resolve
        })
    ) as unknown as typeof fetch
    a.trackPageView()
    a.flushAnalytics()
    prefs.value.analytics_enabled = false
    await a.resetOptOutCache()
    fail(new Response(null, { status: 503 }))
    await vi.runAllTimersAsync()
    expect(sent()).toHaveLength(1)
  })
})

describe('consent withdrawal during pending delivery', () => {
  it('drops usage queued before a decline and cancels retry delivery', async () => {
    const a = await load()
    globalThis.fetch = vi.fn(
      async () => new Response(null, { status: 503 })
    ) as unknown as typeof fetch
    a.trackPageView()
    a.flushAnalytics()
    await vi.advanceTimersByTimeAsync(0)
    a.trackEvent('Backup', 'Start')
    a.trackConsentResponse(false)
    expect(a.getAnalyticsInstanceKey()).toBeNull()
    await vi.runAllTimersAsync()
    expect(sent().filter((event) => event.name === 'pageview')).toHaveLength(1)
    expect(sent().filter((event) => event.name === 'Backup - Start')).toHaveLength(0)
  })

  it('does not send unknown versions as a fabricated value', async () => {
    vi.stubEnv('VITE_APP_VERSION', '')
    const a = await load()
    a.trackPageView()
    a.flushAnalytics()
    expect(sent()[0]).not.toHaveProperty('app_version')
  })

  it('cannot revive queued startup errors or pageviews by learning a version after opting out', async () => {
    const a = await load()
    a.enqueueErrorReport({ message: 'early failure' })
    a.trackPageView()
    a.trackOptOut()
    a.setAppVersion('2.4.2')
    await vi.runAllTimersAsync()
    expect(sent().map((event) => event.name)).toEqual(['Settings - OptOut'])
  })
})

describe('preference response ordering', () => {
  it('does not reopen tracking when a stale preference response settles after opt-out', async () => {
    const a = await load()
    const req = await import('../../services/authRequest')
    let complete!: (response: Response) => void
    vi.mocked(req.fetchJsonForAuthMode).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        })
    )
    const reloading = a.resetOptOutCache()
    await vi.advanceTimersByTimeAsync(0)
    a.trackOptOut()
    complete(new Response(JSON.stringify({ preferences: prefs.value })))
    await reloading
    expect(a.getAnalyticsInstanceKey()).toBeNull()
    a.trackPageView()
    a.flushAnalytics()
    expect(sent().map((event) => event.name)).toEqual(['Settings - OptOut'])
  })
})

describe('bounded analytics delivery', () => {
  it('times out hung requests and stops after bounded attempts', async () => {
    const a = await load()
    globalThis.fetch = vi.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch
    a.trackPageView()
    a.flushAnalytics()
    await vi.runAllTimersAsync()
    expect(fetchMock()).toHaveBeenCalledTimes(3)
    for (const [, init] of fetchMock().mock.calls) expect(init.signal.aborted).toBe(true)
  })

  it('caps simultaneous detached batches while the endpoint hangs', async () => {
    const a = await load()
    globalThis.fetch = vi.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch
    for (let i = 0; i < 500; i++) a.trackEvent('Backup', 'Start')
    a.flushAnalytics()
    expect(fetchMock()).toHaveBeenCalledTimes(4)
    a.trackOptOut()
    await vi.runAllTimersAsync()
  })

  it('does not retry events whose delivery window has expired', async () => {
    const a = await load()
    let complete!: (response: Response) => void
    globalThis.fetch = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve
        })
    ) as unknown as typeof fetch
    a.trackPageView()
    a.flushAnalytics()
    vi.setSystemTime(Date.now() + 61_000)
    complete(new Response(null, { status: 503 }))
    await vi.runAllTimersAsync()
    expect(fetchMock()).toHaveBeenCalledTimes(1)
  })
})
