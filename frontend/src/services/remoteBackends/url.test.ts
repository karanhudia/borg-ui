import { describe, expect, it } from 'vitest'
import {
  getLocalApiBaseUrl,
  getLocalWebBaseUrl,
  normalizeRemoteBackendUrl,
  compareBackendVersions,
} from './url'

describe('remote backend URL normalization', () => {
  it('keeps the local backend API base compatible with the existing default', () => {
    expect(getLocalApiBaseUrl()).toBe('/api')
    expect(getLocalWebBaseUrl()).toBe('')
  })

  it.each([
    ['localhost:8000', 'http://localhost:8000/api', 'http://localhost:8000'],
    ['192.168.1.10:8080', 'http://192.168.1.10:8080/api', 'http://192.168.1.10:8080'],
    ['10.0.0.20:9000', 'http://10.0.0.20:9000/api', 'http://10.0.0.20:9000'],
    ['backup.example.com', 'https://backup.example.com/api', 'https://backup.example.com'],
    [
      'https://backup.example.com/api',
      'https://backup.example.com/api',
      'https://backup.example.com',
    ],
    [
      'https://backup.example.com/borg',
      'https://backup.example.com/borg/api',
      'https://backup.example.com/borg',
    ],
    [
      'https://backup.example.com/borg/api/',
      'https://backup.example.com/borg/api',
      'https://backup.example.com/borg',
    ],
  ])('normalizes %s', (input, apiBaseUrl, webBaseUrl) => {
    expect(normalizeRemoteBackendUrl(input)).toEqual({
      apiBaseUrl,
      webBaseUrl,
    })
  })

  it.each(['', '   ', 'ftp://backup.example.com', 'file:///tmp/borg', 'http://'])(
    'rejects invalid input %s',
    (input) => {
      expect(() => normalizeRemoteBackendUrl(input)).toThrow()
    }
  )
})

describe('backend version compatibility', () => {
  it('treats matching major versions as compatible', () => {
    expect(compareBackendVersions('2.2.2-alpha.1', '2.1.0')).toEqual({
      status: 'compatible',
      message: 'Borg UI 2.1.0 is compatible with this frontend.',
    })
  })

  it('blocks mismatched major versions', () => {
    expect(compareBackendVersions('2.2.2-alpha.1', '3.0.0')).toEqual({
      status: 'incompatible',
      message: 'Borg UI 3.0.0 uses a different major version than this frontend.',
    })
  })

  it('marks missing or unparsable versions as unknown', () => {
    expect(compareBackendVersions('2.2.2-alpha.1', null)).toEqual({
      status: 'unknown',
      message: 'Remote backend version is unavailable.',
    })
    expect(compareBackendVersions('dev', 'nightly')).toEqual({
      status: 'unknown',
      message: 'Remote backend version could not be compared.',
    })
    expect(compareBackendVersions('2.2.2-alpha.1', '2abc')).toEqual({
      status: 'unknown',
      message: 'Remote backend version could not be compared.',
    })
  })
})
