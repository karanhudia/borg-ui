import { createWriteStream } from 'node:fs'
import { mkdir, mkdtemp, readFile, stat, writeFile } from 'node:fs/promises'
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

function filledPixels(color, width, height) {
  return Array.from({ length: width * height }, () => color)
}

function pixelsWithChanges(baseColor, changedColor, changedPixels, width, height) {
  const pixels = filledPixels(baseColor, width, height)

  for (let index = 0; index < changedPixels; index += 1) {
    pixels[index] = changedColor
  }

  return pixels
}

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

  it('ignores tiny unrelated drift while keeping screenshots linked to changed stories', async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'borg-visual-relevance-'))
    const baselineDir = path.join(root, 'baseline')
    const actualDir = path.join(root, 'actual')
    const outputDir = path.join(root, 'report')
    const sourceRoot = path.join(root, 'source')
    const storyPath = path.join(sourceRoot, 'frontend/src/components/Thing.stories.tsx')

    await mkdir(path.dirname(storyPath), { recursive: true })
    await writeFile(storyPath, "export default { title: 'Components/Thing' }\n")

    await writePng(
      path.join(baselineDir, 'components-thing--minor-icon.png'),
      filledPixels(white, 100, 100),
      100,
      100
    )
    await writePng(
      path.join(actualDir, 'components-thing--minor-icon.png'),
      pixelsWithChanges(white, red, 1, 100, 100),
      100,
      100
    )

    await writePng(
      path.join(baselineDir, 'components-other--tiny-drift.png'),
      filledPixels(white, 100, 100),
      100,
      100
    )
    await writePng(
      path.join(actualDir, 'components-other--tiny-drift.png'),
      pixelsWithChanges(white, blue, 1, 100, 100),
      100,
      100
    )

    await writePng(
      path.join(baselineDir, 'components-other--large-change.png'),
      filledPixels(white, 100, 100),
      100,
      100
    )
    await writePng(
      path.join(actualDir, 'components-other--large-change.png'),
      pixelsWithChanges(white, red, 20, 100, 100),
      100,
      100
    )

    const summary = await compareVisualSnapshots({
      baselineDir,
      actualDir,
      outputDir,
      sourceRoot,
      changedFiles: ['frontend/src/components/Thing.stories.tsx'],
      unrelatedDiffThreshold: 0.001,
    })

    expect(summary.changed.map((item) => item.fileName)).toEqual([
      'components-other--large-change.png',
      'components-thing--minor-icon.png',
    ])
    expect(summary.unchanged).toContainEqual({ fileName: 'components-other--tiny-drift.png' })
    expect(summary.totals.changed).toBe(2)
    expect(summary.totals.unchanged).toBe(1)
  })

  it('uses the tiny drift threshold when no changed story can be mapped', async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'borg-visual-unmapped-'))
    const baselineDir = path.join(root, 'baseline')
    const actualDir = path.join(root, 'actual')
    const outputDir = path.join(root, 'report')

    await writePng(
      path.join(baselineDir, 'components-one--tiny-drift.png'),
      filledPixels(white, 100, 100),
      100,
      100
    )
    await writePng(
      path.join(actualDir, 'components-one--tiny-drift.png'),
      pixelsWithChanges(white, blue, 1, 100, 100),
      100,
      100
    )

    await writePng(
      path.join(baselineDir, 'components-two--large-change.png'),
      filledPixels(white, 100, 100),
      100,
      100
    )
    await writePng(
      path.join(actualDir, 'components-two--large-change.png'),
      pixelsWithChanges(white, red, 20, 100, 100),
      100,
      100
    )

    const summary = await compareVisualSnapshots({
      baselineDir,
      actualDir,
      outputDir,
      changedFiles: ['frontend/scripts/visual-regression-report.mjs'],
      unrelatedDiffThreshold: 0.001,
    })

    expect(summary.changed.map((item) => item.fileName)).toEqual([
      'components-two--large-change.png',
    ])
    expect(summary.unchanged).toContainEqual({ fileName: 'components-one--tiny-drift.png' })
    expect(summary.totals.changed).toBe(1)
    expect(summary.totals.unchanged).toBe(1)
  })
})
