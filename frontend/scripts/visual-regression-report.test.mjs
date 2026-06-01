import { createWriteStream } from 'node:fs'
import { mkdir, mkdtemp, readFile, stat } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

import { PNG } from 'pngjs'
import { describe, expect, it } from 'vitest'

import { compareVisualSnapshots } from './visual-regression-report.mjs'

async function writePng(filePath, pixels, width = 2, height = 2) {
  const png = new PNG({ width, height })
  pixels.forEach(([r, g, b, a], index) => {
    const offset = index * 4
    png.data[offset] = r
    png.data[offset + 1] = g
    png.data[offset + 2] = b
    png.data[offset + 3] = a
  })
  await mkdir(path.dirname(filePath), { recursive: true })
  await new Promise((resolve, reject) => {
    png.pack().pipe(createWriteStream(filePath)).on('finish', resolve).on('error', reject)
  })
}

const white = [255, 255, 255, 255]
const black = [0, 0, 0, 255]
const red = [255, 0, 0, 255]
const blue = [0, 0, 255, 255]

describe('compareVisualSnapshots', () => {
  it('classifies changed, added, removed, and unchanged screenshots', async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'borg-visual-report-'))
    const baselineDir = path.join(root, 'baseline')
    const actualDir = path.join(root, 'actual')
    const outputDir = path.join(root, 'report')

    await writePng(path.join(baselineDir, 'changed.png'), [white, white, white, white])
    await writePng(path.join(actualDir, 'changed.png'), [white, red, white, white])
    await writePng(path.join(baselineDir, 'unchanged.png'), [black, black, black, black])
    await writePng(path.join(actualDir, 'unchanged.png'), [black, black, black, black])
    await writePng(path.join(actualDir, 'added.png'), [blue, blue, blue, blue])
    await writePng(path.join(baselineDir, 'removed.png'), [red, red, red, red])

    const summary = await compareVisualSnapshots({
      baselineDir,
      actualDir,
      outputDir,
      reportUrl: 'https://docs.example.test/visual/reports/pr-1/',
      metadata: {
        title: 'PR 1 visual report',
        commitSha: 'abc1234',
        runUrl: 'https://github.example.test/run',
      },
    })

    expect(summary.totals).toMatchObject({
      added: 1,
      changed: 1,
      removed: 1,
      unchanged: 1,
      baseline: 3,
      actual: 3,
    })
    expect(summary.changed[0]).toMatchObject({
      fileName: 'changed.png',
      diffPixels: 1,
      totalPixels: 4,
    })
    expect(summary.added[0].fileName).toBe('added.png')
    expect(summary.removed[0].fileName).toBe('removed.png')

    await expect(stat(path.join(outputDir, 'images', 'diff', 'changed.png'))).resolves.toBeTruthy()
    await expect(stat(path.join(outputDir, 'summary.json'))).resolves.toBeTruthy()

    const html = await readFile(path.join(outputDir, 'index.html'), 'utf8')
    expect(html).toContain('PR 1 visual report')
    expect(html).toContain('Changed')
    expect(html).toContain('Added')
    expect(html).toContain('Removed')
    expect(html).toContain('changed.png')
  })

  it('treats dimension mismatches as changed screenshots', async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'borg-visual-size-'))
    const baselineDir = path.join(root, 'baseline')
    const actualDir = path.join(root, 'actual')
    const outputDir = path.join(root, 'report')

    await writePng(path.join(baselineDir, 'resized.png'), [white, white, white, white], 2, 2)
    await writePng(path.join(actualDir, 'resized.png'), [white], 1, 1)

    const summary = await compareVisualSnapshots({ baselineDir, actualDir, outputDir })

    expect(summary.totals.changed).toBe(1)
    expect(summary.changed[0]).toMatchObject({
      fileName: 'resized.png',
      dimensionsChanged: true,
    })
  })
})
