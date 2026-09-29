import { afterEach, describe, expect, it, vi } from 'vitest'
import { randomUuid } from '../uuid'

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

describe('randomUuid', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses crypto.randomUUID when the page is a secure context', () => {
    expect(randomUuid()).toMatch(UUID4)
  })

  // Plain http on a LAN address is not a secure context, so randomUUID is
  // missing there while getRandomValues is not (issue #1241).
  it('builds a v4 from getRandomValues when randomUUID is missing', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (values: Uint8Array) => values.fill(0xff),
    })
    expect(randomUuid()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff')
  })
})
