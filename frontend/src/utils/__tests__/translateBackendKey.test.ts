import { describe, it, expect, vi } from 'vitest'

// Mock i18n BEFORE importing the utility so the mock is in place
vi.mock('../../i18n', () => ({
  default: {
    t: (key: string, params?: Record<string, unknown>) => {
      if (params && Object.keys(params).length > 0) {
        return `${key}(${JSON.stringify(params)})`
      }
      return key
    },
  },
}))

import { translateBackendKey } from '../translateBackendKey'

describe('translateBackendKey', () => {
  it('Shape 1: {key, params} object — calls i18n.t with key and params', () => {
    expect(translateBackendKey({ key: 'errors.repo.not_found', params: { name: 'myrepo' } })).toBe(
      'errors.repo.not_found({"name":"myrepo"})',
    )
  })

  it('Shape 1: {key} object without params — calls i18n.t with key only', () => {
    expect(translateBackendKey({ key: 'errors.auth.invalid_credentials' })).toBe(
      'errors.auth.invalid_credentials',
    )
  })

  it('Shape 2: JSON-encoded {key, params} string — parses and translates', () => {
    expect(translateBackendKey('{"key":"errors.borg.lock","params":{}}')).toBe('errors.borg.lock')
  })

  it('Shape 2: JSON-encoded {key} string without params — parses and translates', () => {
    expect(translateBackendKey('{"key":"backend.errors.auth.not_found"}')).toBe(
      'backend.errors.auth.not_found',
    )
  })

  it('Shape 3: dot-notation key string — passes to i18n.t directly', () => {
    expect(translateBackendKey('errors.auth.invalid_credentials')).toBe(
      'errors.auth.invalid_credentials',
    )
  })

  it('Shape 4: raw English string — returned verbatim (legacy passthrough)', () => {
    expect(translateBackendKey('Repository not found')).toBe('Repository not found')
  })

  it('null — returns default fallback key translation', () => {
    expect(translateBackendKey(null)).toBe('common.errors.unexpectedError')
  })

  it('undefined — returns default fallback key translation', () => {
    expect(translateBackendKey(undefined)).toBe('common.errors.unexpectedError')
  })

  it('malformed JSON string — falls through to raw string passthrough', () => {
    expect(translateBackendKey('{"bad json}')).toBe('{"bad json}')
  })

  it('JSON object without .key property — falls through to raw string passthrough', () => {
    expect(translateBackendKey('{"something":"else"}')).toBe('{"something":"else"}')
  })

  it('custom fallback key overrides default', () => {
    expect(translateBackendKey(null, 'custom.error.key')).toBe('custom.error.key')
  })
})
