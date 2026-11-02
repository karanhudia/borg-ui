import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchAnnouncementsManifest } from '../announcements'
import manifest from '../../data/announcements.json'

afterEach(() => vi.unstubAllEnvs())

function mockResponse(value: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => value }))
}

describe('announcement manifest boundary', () => {
  it('preserves the valid published announcement schema', async () => {
    mockResponse(manifest)
    expect(await fetchAnnouncementsManifest()).toEqual(manifest)
  })

  it('discards malformed entries and preserves valid neighbors', async () => {
    mockResponse({ version: 1, announcements: [null, {}, false, manifest.announcements[0]] })
    expect((await fetchAnnouncementsManifest()).announcements).toEqual([manifest.announcements[0]])
  })

  it.each(
    [null, [], 1, {}, { announcements: null }, { announcements: 'bad' }].map((value) => [value])
  )('rejects malformed envelopes: %j', async (value) => {
    mockResponse(value)
    await expect(fetchAnnouncementsManifest()).rejects.toThrow(
      'Failed to fetch announcements manifest'
    )
  })

  it('falls back to the bundled URL when the production response is invalid JSON', async () => {
    vi.stubEnv('DEV', false)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => {
          throw new SyntaxError('Invalid JSON')
        },
      })
      .mockResolvedValueOnce({ ok: true, json: async () => manifest })
    vi.stubGlobal('fetch', fetchMock)
    expect(await fetchAnnouncementsManifest('/local.json')).toEqual(manifest)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'https://updates.borgui.com/announcements.json',
      '/local.json',
    ])
  })
})
