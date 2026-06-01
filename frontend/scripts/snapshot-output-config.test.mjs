import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { resolveSnapshotOutputDir } from './snapshot-output-config.mjs'
import { buildArgosUploadArgs } from './upload-argos-snapshots.mjs'

describe('resolveSnapshotOutputDir', () => {
  it('defaults to the ignored Argos screenshots directory', () => {
    expect(resolveSnapshotOutputDir('/repo/frontend', {})).toBe(
      path.join('/repo/frontend', 'argos-screenshots')
    )
  })

  it('resolves relative STORYBOOK_SNAPSHOTS_DIR values from the frontend root', () => {
    expect(
      resolveSnapshotOutputDir('/repo/frontend', {
        STORYBOOK_SNAPSHOTS_DIR: 'tmp/storybook-screenshots',
      })
    ).toBe(path.join('/repo/frontend', 'tmp/storybook-screenshots'))
  })

  it('preserves absolute STORYBOOK_SNAPSHOTS_DIR values for targeted proof runs', () => {
    expect(
      resolveSnapshotOutputDir('/repo/frontend', {
        STORYBOOK_SNAPSHOTS_DIR: '/tmp/storybook-screenshots',
      })
    ).toBe('/tmp/storybook-screenshots')
  })
})

describe('buildArgosUploadArgs', () => {
  it('uploads the same directory selected by the snapshot output resolver', () => {
    expect(
      buildArgosUploadArgs('/repo/frontend', {
        STORYBOOK_SNAPSHOTS_DIR: 'tmp/storybook-screenshots',
      })
    ).toEqual([
      'exec',
      '--',
      'argos',
      'upload',
      path.join('/repo/frontend', 'tmp/storybook-screenshots'),
    ])
  })
})
