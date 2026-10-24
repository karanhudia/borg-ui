import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import * as analytics from '../analytics'
import { trackApiError } from '../analytics'
import {
  fnv1a64,
  installGlobalErrorHandlers,
  normalizeMessage,
  reportError,
  resetErrorReporting,
  scrubSecrets,
} from '../errorReporting'

const spyOnEnqueue = () => vi.spyOn(analytics, 'enqueueErrorReport').mockImplementation(() => {})

beforeEach(() => {
  vi.useFakeTimers()
  resetErrorReporting()
  window.history.pushState({}, '', '/repositories/12')
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('fnv1a64', () => {
  it('hashes with FNV-1a 64', () => {
    expect(fnv1a64('')).toBe('cbf29ce484222325')
    expect(fnv1a64('a')).toBe('af63dc4c8601ec8c')
  })
  it('pads to 16 hex chars and hashes UTF-8 bytes', () => {
    expect(fnv1a64('x')).toMatch(/^[0-9a-f]{16}$/)
    expect(fnv1a64('é')).not.toBe(fnv1a64('e'))
  })
})

describe('normalizeMessage', () => {
  it('normalizes volatile parts of a message', () => {
    expect(normalizeMessage("Repo '/mnt/backup/photos' id 42 (3f2a9c1d7b) not found")).toBe(
      'Repo <str> id <n> (<hex>) not found'
    )
  })
  it('replaces uuids before hex, and unquoted paths', () => {
    expect(normalizeMessage('job 123e4567-e89b-12d3-a456-426614174000 failed')).toBe(
      'job <uuid> failed'
    )
    expect(normalizeMessage('cannot read /mnt/a/b and C:\\Users\\x')).toBe(
      'cannot read <path> and <path>'
    )
  })
})

describe('scrubSecrets', () => {
  it('scrubs secrets but keeps paths and hosts', () => {
    const out = scrubSecrets(
      'BORG_PASSPHRASE=hunter2 borg create ssh://me@nas.local/./repo Authorization: Bearer abc.def'
    )
    expect(out).not.toContain('hunter2')
    expect(out).not.toContain('abc.def')
    expect(out).toContain('ssh://me@nas.local/./repo')
    expect(
      scrubSecrets('-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----')
    ).toBe('[redacted]')
  })
  it('scrubs a truncated key block, keyed values and rclone config', () => {
    expect(scrubSecrets('x -----BEGIN RSA PRIVATE KEY-----\nAAAA')).toBe('x [redacted]')
    const out = scrubSecrets(
      'token=t1 password="p 2" secret=s3 key=k4 pass = p5 secret_access_key = s6 client_secret=c7 BORG_NEW_PASSPHRASE=n8 passphrase=p9 use Bearer zzz'
    )
    for (const v of ['t1', 'p 2', 's3', 'k4', 'p5', 's6', 'c7', 'n8', 'p9', 'zzz']) {
      expect(out).not.toContain(v)
    }
    expect(out).toContain('use Bearer [redacted]')
  })
  it('scrubs prefixed key names but keeps paths and hosts', () => {
    const out = scrubSecrets(
      'api_key=AAA aws_secret_access_key = BBB x_token=CCC at /mnt/a/b ssh://me@nas.local/./repo'
    )
    for (const v of ['AAA', 'BBB', 'CCC']) expect(out).not.toContain(v)
    expect(out).toContain('/mnt/a/b ssh://me@nas.local/./repo')
  })
})

describe('reportError', () => {
  it('sends the Event shape props', () => {
    const sent = spyOnEnqueue()
    reportError(new TypeError('boom BORG_PASSPHRASE=hunter2'), { kind: 'render', component: 'Foo' })
    expect(sent).toHaveBeenCalledTimes(1)
    const props = sent.mock.calls[0][0]
    expect(props).toMatchObject({
      origin: 'frontend',
      kind: 'render',
      type: 'TypeError',
      message: 'boom BORG_PASSPHRASE=[redacted]',
      component: 'Foo',
      route: '/repositories/:id',
      count: 1,
    })
    expect(props.fingerprint).toMatch(/^[0-9a-f]{16}$/)
    expect(props.stack).not.toContain('hunter2')
  })

  it('truncates message to 500 and stack to 8192', () => {
    const sent = spyOnEnqueue()
    const e = new Error('m'.repeat(900))
    e.stack = 's'.repeat(9000)
    reportError(e, { kind: 'uncaught' })
    expect(sent.mock.calls[0][0].message).toHaveLength(500)
    expect(sent.mock.calls[0][0].stack).toHaveLength(8192)
  })

  it('fingerprints ignore volatile message parts and use the first same-origin frame', () => {
    const sent = spyOnEnqueue()
    const make = (id: number, line: number) => {
      const e = new Error(`repo ${id} missing`)
      e.stack = [
        'Error: x',
        '    at foreign (https://cdn.example.com/lib.js:1:1)',
        `    at doThing (${window.location.origin}/assets/app-abc.js:${line}:9)`,
      ].join('\n')
      return e
    }
    reportError(make(1, 10), { kind: 'uncaught' })
    vi.advanceTimersByTime(11 * 60 * 1000)
    reportError(make(2, 99), { kind: 'uncaught' })
    expect(sent.mock.calls[1][0].fingerprint).toBe(sent.mock.calls[0][0].fingerprint)
    expect(sent.mock.calls[0][0].fingerprint).toBe(
      fnv1a64(['frontend', 'uncaught', 'Error', 'doThing@app-abc.js', 'repo <n> missing'].join('|'))
    )
  })

  it('reads a Firefox style frame', () => {
    const sent = spyOnEnqueue()
    const e = new Error('x')
    e.stack = `render@${window.location.origin}/assets/a.js:3:4`
    reportError(e, { kind: 'uncaught' })
    expect(sent.mock.calls[0][0].fingerprint).toBe(
      fnv1a64(['frontend', 'uncaught', 'Error', 'render@a.js', 'x'].join('|'))
    )
  })

  it('fingerprints api errors from method, area, status and key', () => {
    const sent = spyOnEnqueue()
    reportError(new Error('Request failed'), {
      kind: 'api',
      method: 'post',
      area: 'repositories',
      status: 409,
      error_key: 'exists',
    })
    reportError(new Error('x'), { kind: 'api', method: 'get', area: 'a' })
    expect(sent.mock.calls[0][0]).toMatchObject({
      kind: 'api',
      method: 'post',
      area: 'repositories',
      status: 409,
      error_key: 'exists',
      fingerprint: fnv1a64('api|post|repositories|409|exists'),
    })
    expect(sent.mock.calls[1][0].fingerprint).toBe(fnv1a64('api|get|a|network|'))
  })

  it('sends one report then folds repeats into count', () => {
    const sent = spyOnEnqueue()
    for (let i = 0; i < 100; i++) reportError(new TypeError('boom'), { kind: 'uncaught' })
    expect(sent).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(10 * 60 * 1000)
    reportError(new TypeError('boom'), { kind: 'uncaught' })
    expect(sent).toHaveBeenCalledTimes(2)
    expect(sent.mock.calls[1][0]).toMatchObject({ count: 100 })
  })

  it('caps reports at 30 per hour and recovers after it', () => {
    const sent = spyOnEnqueue()
    for (let i = 0; i < 50; i++)
      reportError(new Error(`distinct ${'x'.repeat(i)}`), { kind: 'uncaught' })
    expect(sent).toHaveBeenCalledTimes(30)
    vi.advanceTimersByTime(61 * 60 * 1000)
    reportError(new Error('another'), { kind: 'uncaught' })
    expect(sent).toHaveBeenCalledTimes(31)
  })

  it('never throws, whatever is thrown', () => {
    const circular: Record<string, unknown> = {}
    circular.self = circular
    const hostile = {
      get message(): string {
        throw new Error('no')
      },
    }
    for (const value of [null, undefined, 'a string', 42, circular, Object.create(null), hostile]) {
      expect(() => reportError(value, { kind: 'rejection' })).not.toThrow()
    }
  })

  it('never throws when sending throws', () => {
    vi.spyOn(analytics, 'enqueueErrorReport').mockImplementation(() => {
      throw new Error('send failed')
    })
    expect(() => reportError(new Error('x'), { kind: 'uncaught' })).not.toThrow()
  })

  it('drops the stack, not the report, when props are too large', () => {
    const sent = spyOnEnqueue()
    const e = new Error('keep me')
    e.stack = '\n'.repeat(9000)
    reportError(e, { kind: 'uncaught' })
    const props = sent.mock.calls[0][0]
    expect(props.stack).toBeUndefined()
    expect(props.message).toBe('keep me')
    expect(JSON.stringify(props).length).toBeLessThanOrEqual(16384)
  })

  it('caps the type at 100 characters', () => {
    const sent = spyOnEnqueue()
    const e = new Error('x')
    e.name = 'N'.repeat(5000)
    reportError(e, { kind: 'uncaught' })
    expect(sent.mock.calls[0][0].type).toHaveLength(100)
  })
})

describe('global handlers', () => {
  const rejection = (reason: unknown) =>
    window.dispatchEvent(Object.assign(new Event('unhandledrejection'), { reason }))

  it('reports uncaught errors and rejections once installed twice', () => {
    const sent = spyOnEnqueue()
    installGlobalErrorHandlers()
    installGlobalErrorHandlers()
    window.dispatchEvent(new ErrorEvent('error', { message: 'x', error: new TypeError('boom') }))
    rejection(new RangeError('later'))
    expect(sent).toHaveBeenCalledTimes(2)
    expect(sent.mock.calls[0][0]).toMatchObject({ kind: 'uncaught', type: 'TypeError' })
    expect(sent.mock.calls[1][0]).toMatchObject({ kind: 'rejection', type: 'RangeError' })
  })

  it('reports a same-origin error and falls back to the message', () => {
    const sent = spyOnEnqueue()
    installGlobalErrorHandlers()
    window.dispatchEvent(
      new ErrorEvent('error', { message: 'plain', filename: `${window.location.origin}/a.js` })
    )
    expect(sent.mock.calls[0][0]).toMatchObject({ kind: 'uncaught', message: 'plain' })
  })

  it('ignores cross-origin and extension errors', () => {
    const sent = spyOnEnqueue()
    installGlobalErrorHandlers()
    window.dispatchEvent(new ErrorEvent('error', { message: 'Script error.' }))
    window.dispatchEvent(
      new ErrorEvent('error', {
        message: 'x',
        filename: 'chrome-extension://abc/content.js',
        error: new Error('x'),
      })
    )
    expect(sent).not.toHaveBeenCalled()
  })

  it('ignores a look-alike host and an unparsable filename', () => {
    const sent = spyOnEnqueue()
    installGlobalErrorHandlers()
    for (const filename of [
      `${window.location.origin}.evil.com/a.js`,
      'https://a.com.evil.com/a.js',
      'http://',
    ]) {
      window.dispatchEvent(
        new ErrorEvent('error', { message: 'x', filename, error: new Error('x') })
      )
    }
    expect(sent).not.toHaveBeenCalled()
  })

  it('stops reporting once the page is unloading', () => {
    const sent = spyOnEnqueue()
    installGlobalErrorHandlers()
    window.dispatchEvent(new Event('pagehide'))
    rejection(new Error('aborted by reload'))
    trackApiError({ isAxiosError: true, config: { method: 'get', url: '/x' } })
    expect(sent).not.toHaveBeenCalled()
  })

  it('ignores cancelled and aborted rejections', () => {
    const sent = spyOnEnqueue()
    installGlobalErrorHandlers()
    rejection({ code: 'ERR_CANCELED', isAxiosError: true })
    rejection(new axios.CanceledError('cancelled'))
    rejection(new DOMException('aborted', 'AbortError'))
    expect(sent).not.toHaveBeenCalled()
  })
})

describe('trackApiError reporting', () => {
  it('reports failed reads with the error key stripped, skips 5xx and cancels', () => {
    const sent = spyOnEnqueue()
    trackApiError({
      isAxiosError: true,
      config: { method: 'get', url: '/ssh-keys' },
      response: { status: 404, data: { detail: { key: 'backend.errors.ssh.sshKeyNotFound' } } },
    })
    trackApiError({
      isAxiosError: true,
      config: { method: 'post', url: '/repositories' },
      response: { status: 500 },
    })
    trackApiError({
      isAxiosError: true,
      code: 'ERR_CANCELED',
      config: { method: 'get', url: '/repositories' },
    })
    expect(sent).toHaveBeenCalledTimes(1)
    expect(sent.mock.calls[0][0]).toMatchObject({
      kind: 'api',
      area: 'ssh-keys',
      method: 'get',
      status: 404,
      error_key: 'ssh.sshKeyNotFound',
    })
  })

  it('reports a network failure without a status', () => {
    const sent = spyOnEnqueue()
    trackApiError({ isAxiosError: true, config: { method: 'put', url: '/settings' } })
    expect(sent.mock.calls[0][0]).toMatchObject({ kind: 'api', method: 'put' })
    expect(sent.mock.calls[0][0].status).toBeUndefined()
  })
})
