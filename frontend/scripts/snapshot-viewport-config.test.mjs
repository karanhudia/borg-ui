import { describe, expect, it } from 'vitest'

import { snapshotFileName, snapshotViewports } from './snapshot-viewport-config.mjs'

describe('snapshot viewport config', () => {
  it('keeps desktop snapshots on the existing file names', () => {
    const desktop = snapshotViewports.find((viewport) => viewport.id === 'desktop')

    expect(desktop).toMatchObject({ width: 1280, height: 800, fileSuffix: '' })
    expect(snapshotFileName('component--state', desktop)).toBe('component--state.png')
  })

  it('adds a mobile snapshot beside each desktop baseline', () => {
    const mobile = snapshotViewports.find((viewport) => viewport.id === 'mobile')

    expect(mobile).toMatchObject({ width: 390, height: 844, fileSuffix: '--mobile' })
    expect(snapshotFileName('component--state', mobile)).toBe('component--state--mobile.png')
  })
})
