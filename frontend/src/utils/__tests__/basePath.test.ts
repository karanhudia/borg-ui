import { describe, it, expect, vi, afterEach } from 'vitest'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('basePath', () => {
  it('converts "/" to empty string', async () => {
    vi.stubGlobal('__BASE_PATH__', '/')
    vi.resetModules()
    const { BASE_PATH } = await import('../basePath')
    expect(BASE_PATH).toBe('')
  })

  it('returns a non-slash path as-is', async () => {
    vi.stubGlobal('__BASE_PATH__', '/borg-ui')
    vi.resetModules()
    const { BASE_PATH } = await import('../basePath')
    expect(BASE_PATH).toBe('/borg-ui')
  })

  it('defaults to empty string when unset', async () => {
    vi.resetModules()
    const { BASE_PATH } = await import('../basePath')
    expect(BASE_PATH).toBe('')
  })
})
