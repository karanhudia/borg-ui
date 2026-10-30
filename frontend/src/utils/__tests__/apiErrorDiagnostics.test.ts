import { describe, expect, it, vi } from 'vitest'
import { apiErrorDiagnostics, markApiRequest } from '../apiErrorDiagnostics'

describe('allowlisted API diagnostics', () => {
  it('retains endpoint structure without hosts, ids, names, query values or fragments', () => {
    const diagnostic = apiErrorDiagnostics({
      config: {
        method: 'GET',
        url: 'https://private.example/base/api/v2/archives/family-photos/contents?path=/secret&token=secret#private',
      },
      code: 'ETIMEDOUT',
    })
    expect(diagnostic).toMatchObject({
      endpoint: '/v2/archives/:id/contents',
      error_class: 'timeout',
      error_code: 'ETIMEDOUT',
    })
    expect(JSON.stringify(diagnostic)).not.toMatch(/private|family|secret|example/)
  })
  it('uses a safe fallback for unknown endpoints and never emits an arbitrary area', () => {
    expect(
      apiErrorDiagnostics({ config: { url: '/repositories/my-nas/custom-secret' } }).endpoint
    ).toBe('/repositories/:unknown')
    expect(apiErrorDiagnostics({ config: { url: '/private-hostname/secret' } }).endpoint).toBe(
      '/other/:unknown'
    )
  })
  it.each([
    ['ECONNABORTED', 'timeout'],
    ['ERR_NETWORK', 'network'],
    ['ERR_BAD_OPTION', 'configuration'],
    ['ERR_INVALID_URL', 'configuration'],
    ['ERR_BAD_RESPONSE', 'response'],
    ['ERR_FR_TOO_MANY_REDIRECTS', 'response'],
    ['arbitrary-secret-code', 'unknown'],
  ])('classifies %s as %s without copying unknown codes', (code, expected) => {
    const detail = apiErrorDiagnostics({ code, config: { url: '/settings' } })
    expect(detail.error_class).toBe(expected)
    if (expected === 'unknown') expect(detail.error_code).toBeUndefined()
  })
  it.each([
    ['ERR_BAD_REQUEST', 422, 'http'],
    ['ERR_BAD_RESPONSE', 502, 'http'],
    ['ERR_BAD_RESPONSE', 503, 'http'],
    ['ERR_BAD_RESPONSE', 200, 'response'],
    ['ERR_FR_TOO_MANY_REDIRECTS', 302, 'response'],
  ])('classifies %s with HTTP %s as %s', (code, status, expected) => {
    expect(apiErrorDiagnostics({ code, request: {}, response: { status } }).error_class).toBe(
      expected
    )
  })
  it.each([
    ['/source-discovery/apps/inspect', '/source-discovery/apps/inspect'],
    ['/system/licensing/feature-trial', '/system/licensing/feature-trial'],
    ['/settings/tokens', '/settings/tokens'],
    [
      '/repositories/private-name/prune/comparison/refresh?auto=true&token=private-token',
      '/repositories/:id/prune/comparison/refresh',
    ],
    ['/backup-plans/from-repository/private-name', '/backup-plans/from-repository/:id'],
  ])('captures the fixed template for %s', (url, expected) => {
    const diagnostic = apiErrorDiagnostics({ config: { url } })
    expect(diagnostic.endpoint).toBe(expected)
    expect(JSON.stringify(diagnostic)).not.toContain('private-name')
    expect(JSON.stringify(diagnostic)).not.toContain('private-token')
  })
  it('distinguishes a response from a request that received no response', () => {
    expect(apiErrorDiagnostics({ response: { status: 502 } }).error_class).toBe('http')
    expect(apiErrorDiagnostics({ request: {} }).error_class).toBe('network')
    expect(apiErrorDiagnostics({}).error_class).toBe('unknown')
  })
  it('retains response failures even when Axios has a request object', () => {
    expect(apiErrorDiagnostics({ code: 'ERR_BAD_RESPONSE', request: {} }).error_class).toBe(
      'response'
    )
  })
  it('only captures opaque request ids supplied by the server', () => {
    expect(
      apiErrorDiagnostics({
        response: { headers: { 'x-request-id': '123e4567-e89b-12d3-a456-426614174000' } },
      }).request_id
    ).toBe('123e4567-e89b-12d3-a456-426614174000')
    expect(
      apiErrorDiagnostics({ response: { headers: { 'x-request-id': 'private customer name' } } })
        .request_id
    ).toBeUndefined()
  })
  it('records elapsed time and timeout separately without including the request config', () => {
    vi.spyOn(performance, 'now').mockReturnValue(100)
    const config = markApiRequest({
      url: '/settings',
      timeout: 30000,
      headers: { Authorization: 'private' },
      data: 'private',
    })
    vi.spyOn(performance, 'now').mockReturnValue(350)
    expect(apiErrorDiagnostics({ config, code: 'ETIMEDOUT' })).toMatchObject({
      duration_ms: 250,
      timeout_ms: 30000,
    })
    expect(JSON.stringify(apiErrorDiagnostics({ config }))).not.toContain('private')
    vi.restoreAllMocks()
  })
})
