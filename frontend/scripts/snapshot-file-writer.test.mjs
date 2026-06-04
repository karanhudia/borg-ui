import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

import pngjs from 'pngjs'
import { describe, expect, it } from 'vitest'

import { writeSnapshotIfChanged } from './snapshot-file-writer.mjs'

const { PNG } = pngjs

function makePngBuffer(filterType) {
  const png = new PNG({ width: 1, height: 1 })
  png.data.set([17, 34, 51, 255])
  return PNG.sync.write(png, { filterType })
}

describe('writeSnapshotIfChanged', () => {
  it('keeps the committed PNG when a new capture has identical pixels but different bytes', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'borg-storybook-snapshot-'))

    try {
      const outputPath = path.join(tempRoot, 'storybook-snapshots', 'component--state.png')
      const committedPng = makePngBuffer(0)
      const recapturedPng = makePngBuffer(4)
      expect(recapturedPng.equals(committedPng)).toBe(false)

      await mkdir(path.dirname(outputPath), { recursive: true })
      await writeFile(outputPath, committedPng)

      const result = await writeSnapshotIfChanged(outputPath, recapturedPng)

      await expect(readFile(outputPath)).resolves.toEqual(committedPng)
      expect(result).toEqual({ changed: false, reason: 'matching-pixels' })
    } finally {
      await rm(tempRoot, { force: true, recursive: true })
    }
  })
})
