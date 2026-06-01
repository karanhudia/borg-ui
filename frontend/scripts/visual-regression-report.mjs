#!/usr/bin/env node

import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import pngjs from 'pngjs'

import { resolveSnapshotOutputDir } from './snapshot-output-config.mjs'

const { PNG } = pngjs

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendRoot, '..')

function normalizeFileName(fileName) {
  return fileName.split(path.sep).join('/')
}

function normalizeRelativePath(fileName) {
  return normalizeFileName(fileName).replace(/^\.\//, '')
}

function storyTitleToSnapshotPrefix(title) {
  return title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function snapshotMatchesPrefix(fileName, prefix) {
  const snapshotName = fileName.endsWith('.png') ? fileName.slice(0, -4) : fileName
  return snapshotName === prefix || snapshotName.startsWith(`${prefix}--`)
}

function parseThreshold(value, fallback = 0) {
  if (value === undefined || value === '') {
    return fallback
  }

  const parsed = Number.parseFloat(value)
  if (!Number.isFinite(parsed) || parsed < 0) {
    return fallback
  }

  return parsed
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function assetUrl(fileName, kind) {
  return `images/${kind}/${normalizeFileName(fileName)
    .split('/')
    .map((part) => encodeURIComponent(part))
    .join('/')}`
}

function percent(value) {
  if (!Number.isFinite(value)) {
    return '0.00%'
  }

  return `${(value * 100).toFixed(2)}%`
}

async function listPngFiles(rootDir, currentDir = rootDir) {
  let entries

  try {
    entries = await readdir(currentDir, { withFileTypes: true })
  } catch (error) {
    if (currentDir === rootDir && error && error.code === 'ENOENT') {
      return []
    }

    throw error
  }

  const files = []

  for (const entry of entries) {
    const absolutePath = path.join(currentDir, entry.name)

    if (entry.isDirectory()) {
      files.push(...(await listPngFiles(rootDir, absolutePath)))
      continue
    }

    if (entry.isFile() && entry.name.toLowerCase().endsWith('.png')) {
      files.push(normalizeFileName(path.relative(rootDir, absolutePath)))
    }
  }

  return files.sort((a, b) => a.localeCompare(b))
}

async function readPng(filePath) {
  return PNG.sync.read(await readFile(filePath))
}

async function readLines(filePath) {
  if (!filePath) {
    return []
  }

  const content = await readFile(filePath, 'utf8')
  return content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

async function readStoryTitle(storyPath) {
  try {
    const storySource = await readFile(storyPath, 'utf8')
    return storySource.match(/title:\s*['"`]([^'"`]+)['"`]/)?.[1] || ''
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return ''
    }

    throw error
  }
}

async function snapshotPrefixForChangedFile(fileName, sourceRoot) {
  const relativeFileName = normalizeRelativePath(fileName)

  if (!relativeFileName.startsWith('frontend/src/')) {
    return ''
  }

  const sourcePath = path.join(sourceRoot, relativeFileName)
  const extension = path.extname(relativeFileName)
  const basename = path.basename(relativeFileName, extension)
  const candidateStoryPaths = relativeFileName.includes('.stories.')
    ? [sourcePath]
    : ['.tsx', '.ts', '.jsx', '.js'].map((storyExtension) =>
        path.join(path.dirname(sourcePath), `${basename}.stories${storyExtension}`)
      )

  for (const storyPath of candidateStoryPaths) {
    const title = await readStoryTitle(storyPath)

    if (title) {
      return storyTitleToSnapshotPrefix(title)
    }
  }

  return ''
}

async function resolveRelevantSnapshotPrefixes({ changedFiles, changedFilesPath, sourceRoot }) {
  const fileNames = [...(changedFiles || []), ...(await readLines(changedFilesPath))]
  const prefixes = new Set()

  for (const fileName of fileNames) {
    const prefix = await snapshotPrefixForChangedFile(fileName, sourceRoot)

    if (prefix) {
      prefixes.add(prefix)
    }
  }

  return prefixes
}

async function copySnapshot(sourceRoot, outputDir, kind, fileName) {
  const sourcePath = path.join(sourceRoot, fileName)
  const outputPath = path.join(outputDir, 'images', kind, fileName)
  await mkdir(path.dirname(outputPath), { recursive: true })
  await copyFile(sourcePath, outputPath)
  return assetUrl(fileName, kind)
}

function makeDiffPng(baseline, actual) {
  const width = Math.max(baseline.width, actual.width)
  const height = Math.max(baseline.height, actual.height)
  const diff = new PNG({ width, height })
  let diffPixels = 0

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const outputOffset = (width * y + x) * 4
      const hasBaselinePixel = x < baseline.width && y < baseline.height
      const hasActualPixel = x < actual.width && y < actual.height
      let changed = hasBaselinePixel !== hasActualPixel

      if (hasBaselinePixel && hasActualPixel) {
        const baselineOffset = (baseline.width * y + x) * 4
        const actualOffset = (actual.width * y + x) * 4
        changed =
          baseline.data[baselineOffset] !== actual.data[actualOffset] ||
          baseline.data[baselineOffset + 1] !== actual.data[actualOffset + 1] ||
          baseline.data[baselineOffset + 2] !== actual.data[actualOffset + 2] ||
          baseline.data[baselineOffset + 3] !== actual.data[actualOffset + 3]
      }

      if (changed) {
        diffPixels += 1
        diff.data[outputOffset] = 220
        diff.data[outputOffset + 1] = 38
        diff.data[outputOffset + 2] = 38
        diff.data[outputOffset + 3] = 255
      } else {
        diff.data[outputOffset] = 241
        diff.data[outputOffset + 1] = 245
        diff.data[outputOffset + 2] = 249
        diff.data[outputOffset + 3] = 255
      }
    }
  }

  return {
    diff,
    diffPixels,
    dimensionsChanged: baseline.width !== actual.width || baseline.height !== actual.height,
    totalPixels: width * height,
  }
}

async function writeDiff(outputDir, fileName, diff) {
  const diffPath = path.join(outputDir, 'images', 'diff', fileName)
  await mkdir(path.dirname(diffPath), { recursive: true })
  await writeFile(diffPath, PNG.sync.write(diff))
  return assetUrl(fileName, 'diff')
}

function imageBlock(label, src) {
  if (!src) {
    return ''
  }

  return `
    <figure>
      <figcaption>${escapeHtml(label)}</figcaption>
      <a href="${escapeHtml(src)}"><img src="${escapeHtml(src)}" alt="${escapeHtml(label)}"></a>
    </figure>`
}

function statusPill(label, tone) {
  return `<span class="pill pill-${tone}">${escapeHtml(label)}</span>`
}

function screenshotRow(item, type) {
  const meta = []

  if (type === 'changed') {
    meta.push(`${item.diffPixels.toLocaleString()} px changed`)
    meta.push(percent(item.diffRatio))
    if (item.dimensionsChanged) {
      meta.push(
        `${item.baseline.width}x${item.baseline.height} -> ${item.actual.width}x${item.actual.height}`
      )
    }
  }

  return `
    <article class="shot">
      <div class="shot-header">
        <h3>${escapeHtml(item.fileName)}</h3>
        ${meta.length > 0 ? `<p>${escapeHtml(meta.join(' · '))}</p>` : ''}
      </div>
      <div class="image-grid ${type === 'changed' ? '' : 'single'}">
        ${imageBlock('Before', item.baselinePath)}
        ${imageBlock(type === 'removed' ? 'Removed baseline' : 'After', item.actualPath)}
        ${imageBlock('Diff', item.diffPath)}
      </div>
    </article>`
}

function section(title, items, type, emptyText) {
  return `
    <section class="section">
      <div class="section-title">
        <h2>${escapeHtml(title)}</h2>
        <span>${items.length}</span>
      </div>
      ${
        items.length === 0
          ? `<p class="empty">${escapeHtml(emptyText)}</p>`
          : items.map((item) => screenshotRow(item, type)).join('\n')
      }
    </section>`
}

function renderHtml(summary) {
  const title = summary.metadata.title || 'Visual regression report'
  const generatedAt = new Date(summary.generatedAt).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  })
  const hasChanges =
    summary.totals.changed > 0 || summary.totals.added > 0 || summary.totals.removed > 0

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fa;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #637083;
      --border: #d8dee8;
      --accent: #1769aa;
      --changed: #b42318;
      --added: #067647;
      --removed: #7f56d9;
      --shadow: 0 1px 2px rgba(16, 24, 40, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }

    header {
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 28px min(5vw, 56px);
    }

    main {
      display: grid;
      gap: 24px;
      padding: 24px min(5vw, 56px) 48px;
    }

    h1, h2, h3, p { margin: 0; }

    h1 {
      font-size: clamp(1.6rem, 2.2vw, 2.4rem);
      letter-spacing: 0;
      line-height: 1.15;
    }

    .subtitle {
      color: var(--muted);
      margin-top: 8px;
    }

    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-top: 22px;
      max-width: 980px;
    }

    .metric {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 14px 16px;
    }

    .metric strong {
      display: block;
      font-size: 1.6rem;
      line-height: 1.1;
    }

    .metric span {
      color: var(--muted);
      display: block;
      font-size: 0.88rem;
      margin-top: 4px;
    }

    .meta {
      align-items: center;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }

    .pill {
      border: 1px solid var(--border);
      border-radius: 999px;
      color: var(--muted);
      display: inline-flex;
      font-size: 0.84rem;
      padding: 4px 10px;
    }

    .pill-ok { color: var(--added); border-color: #abefc6; background: #ecfdf3; }
    .pill-changed { color: var(--changed); border-color: #fecdca; background: #fef3f2; }
    .pill-info { color: var(--accent); border-color: #b9d6f2; background: #eff8ff; }

    .section {
      display: grid;
      gap: 14px;
    }

    .section-title {
      align-items: center;
      display: flex;
      gap: 10px;
    }

    .section-title h2 {
      font-size: 1.08rem;
      letter-spacing: 0;
    }

    .section-title span {
      background: #e9eef5;
      border-radius: 999px;
      color: var(--muted);
      font-size: 0.82rem;
      padding: 2px 9px;
    }

    .empty {
      color: var(--muted);
      padding: 12px 0;
    }

    .shot {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .shot-header {
      border-bottom: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
      justify-content: space-between;
      padding: 14px 16px;
    }

    .shot-header h3 {
      font-size: 0.96rem;
      overflow-wrap: anywhere;
    }

    .shot-header p {
      color: var(--muted);
      font-size: 0.88rem;
    }

    .image-grid {
      display: grid;
      gap: 1px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      background: var(--border);
    }

    .image-grid.single {
      grid-template-columns: minmax(0, 1fr);
    }

    figure {
      background: #f8fafc;
      margin: 0;
      min-width: 0;
      padding: 12px;
    }

    figcaption {
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 600;
      margin-bottom: 8px;
      text-transform: uppercase;
    }

    img {
      background: white;
      border: 1px solid #e5e7eb;
      display: block;
      height: auto;
      max-width: 100%;
    }

    a {
      color: var(--accent);
      text-decoration: none;
    }

    a:hover { text-decoration: underline; }

    @media (max-width: 820px) {
      header { padding: 22px 18px; }
      main { padding: 18px; }
      .image-grid { grid-template-columns: minmax(0, 1fr); }
    }
  </style>
</head>
<body>
  <header>
    <h1>${escapeHtml(title)}</h1>
    <p class="subtitle">Generated ${escapeHtml(generatedAt)} UTC</p>
    <div class="meta">
      ${statusPill(hasChanges ? 'Visual changes found' : 'No visual changes', hasChanges ? 'changed' : 'ok')}
      ${summary.reportUrl ? `<a class="pill pill-info" href="${escapeHtml(summary.reportUrl)}">Open report URL</a>` : ''}
      ${summary.metadata.commitSha ? statusPill(`Commit ${summary.metadata.commitSha}`, 'info') : ''}
      ${summary.metadata.runUrl ? `<a class="pill pill-info" href="${escapeHtml(summary.metadata.runUrl)}">Workflow run</a>` : ''}
    </div>
    <div class="summary">
      <div class="metric"><strong>${summary.totals.changed}</strong><span>Changed</span></div>
      <div class="metric"><strong>${summary.totals.added}</strong><span>Added</span></div>
      <div class="metric"><strong>${summary.totals.removed}</strong><span>Removed</span></div>
      <div class="metric"><strong>${summary.totals.unchanged}</strong><span>Unchanged</span></div>
      <div class="metric"><strong>${summary.totals.actual}</strong><span>Current screenshots</span></div>
      <div class="metric"><strong>${summary.totals.baseline}</strong><span>Baseline screenshots</span></div>
    </div>
  </header>
  <main>
    ${section('Changed', summary.changed, 'changed', 'No screenshots changed.')}
    ${section('Added', summary.added, 'added', 'No screenshots were added.')}
    ${section('Removed', summary.removed, 'removed', 'No screenshots were removed.')}
  </main>
</body>
</html>`
}

function buildSummary({
  baselineFiles,
  actualFiles,
  changed,
  added,
  removed,
  unchanged,
  metadata,
  reportUrl,
}) {
  return {
    generatedAt: new Date().toISOString(),
    reportUrl: reportUrl || '',
    metadata: {
      title: metadata?.title || 'Visual regression report',
      commitSha: metadata?.commitSha || '',
      runUrl: metadata?.runUrl || '',
    },
    totals: {
      baseline: baselineFiles.length,
      actual: actualFiles.length,
      compared: changed.length + unchanged.length,
      changed: changed.length,
      added: added.length,
      removed: removed.length,
      unchanged: unchanged.length,
    },
    changed,
    added,
    removed,
    unchanged,
  }
}

export async function compareVisualSnapshots({
  baselineDir,
  actualDir,
  outputDir,
  reportUrl = '',
  metadata = {},
  sourceRoot = repoRoot,
  changedFiles = [],
  changedFilesPath = '',
  unrelatedDiffThreshold = 0,
} = {}) {
  if (!baselineDir) {
    throw new Error('compareVisualSnapshots requires a baselineDir.')
  }

  if (!actualDir) {
    throw new Error('compareVisualSnapshots requires an actualDir.')
  }

  if (!outputDir) {
    throw new Error('compareVisualSnapshots requires an outputDir.')
  }

  const baselineFiles = await listPngFiles(baselineDir)
  const actualFiles = await listPngFiles(actualDir)
  const baselineSet = new Set(baselineFiles)
  const actualSet = new Set(actualFiles)
  const added = []
  const changed = []
  const removed = []
  const unchanged = []
  const relevantSnapshotPrefixes = await resolveRelevantSnapshotPrefixes({
    changedFiles,
    changedFilesPath,
    sourceRoot,
  })
  const relevantSnapshotPrefixList = Array.from(relevantSnapshotPrefixes)

  await rm(outputDir, { force: true, recursive: true })
  await mkdir(outputDir, { recursive: true })

  for (const fileName of actualFiles) {
    if (!baselineSet.has(fileName)) {
      added.push({
        fileName,
        actualPath: await copySnapshot(actualDir, outputDir, 'actual', fileName),
      })
    }
  }

  for (const fileName of baselineFiles) {
    if (!actualSet.has(fileName)) {
      removed.push({
        fileName,
        baselinePath: await copySnapshot(baselineDir, outputDir, 'baseline', fileName),
      })
    }
  }

  for (const fileName of baselineFiles.filter((file) => actualSet.has(file))) {
    const baselinePath = path.join(baselineDir, fileName)
    const actualPath = path.join(actualDir, fileName)
    const baseline = await readPng(baselinePath)
    const actual = await readPng(actualPath)
    const { diff, diffPixels, dimensionsChanged, totalPixels } = makeDiffPng(baseline, actual)
    const diffRatio = totalPixels === 0 ? 0 : diffPixels / totalPixels
    const isRelevantSnapshot = relevantSnapshotPrefixList.some((prefix) =>
      snapshotMatchesPrefix(fileName, prefix)
    )
    const isTinyUnrelatedDiff =
      unrelatedDiffThreshold > 0 &&
      !isRelevantSnapshot &&
      !dimensionsChanged &&
      diffPixels > 0 &&
      diffRatio <= unrelatedDiffThreshold

    if ((diffPixels === 0 && !dimensionsChanged) || isTinyUnrelatedDiff) {
      unchanged.push({ fileName })
      continue
    }

    const [copiedBaselinePath, copiedActualPath, diffPath] = await Promise.all([
      copySnapshot(baselineDir, outputDir, 'baseline', fileName),
      copySnapshot(actualDir, outputDir, 'actual', fileName),
      writeDiff(outputDir, fileName, diff),
    ])

    changed.push({
      fileName,
      baselinePath: copiedBaselinePath,
      actualPath: copiedActualPath,
      diffPath,
      diffPixels,
      totalPixels,
      diffRatio,
      dimensionsChanged,
      baseline: {
        width: baseline.width,
        height: baseline.height,
      },
      actual: {
        width: actual.width,
        height: actual.height,
      },
    })
  }

  const summary = buildSummary({
    baselineFiles,
    actualFiles,
    changed,
    added,
    removed,
    unchanged,
    metadata,
    reportUrl,
  })

  await writeFile(path.join(outputDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`)
  await writeFile(path.join(outputDir, 'index.html'), renderHtml(summary))

  return summary
}

function readCliValue(args, name) {
  const index = args.indexOf(name)
  if (index === -1) {
    return undefined
  }

  return args[index + 1]
}

function cliOptions(args = process.argv.slice(2), env = process.env) {
  return {
    baselineDir:
      readCliValue(args, '--baseline-dir') ||
      env.VISUAL_BASELINE_DIR ||
      path.resolve(frontendRoot, '..', 'visual-regression-state', 'visual', 'baseline'),
    actualDir:
      readCliValue(args, '--actual-dir') ||
      env.VISUAL_ACTUAL_DIR ||
      resolveSnapshotOutputDir(frontendRoot, env),
    outputDir:
      readCliValue(args, '--output-dir') ||
      env.VISUAL_REPORT_DIR ||
      path.resolve(frontendRoot, 'visual-report'),
    sourceRoot: readCliValue(args, '--source-root') || env.VISUAL_SOURCE_ROOT || repoRoot,
    changedFilesPath:
      readCliValue(args, '--changed-files-path') || env.VISUAL_CHANGED_FILES_PATH || '',
    unrelatedDiffThreshold: parseThreshold(
      readCliValue(args, '--unrelated-diff-threshold') || env.VISUAL_UNRELATED_DIFF_THRESHOLD,
      0
    ),
    reportUrl: readCliValue(args, '--report-url') || env.VISUAL_REPORT_URL || '',
    metadata: {
      title: readCliValue(args, '--title') || env.VISUAL_REPORT_TITLE || 'Visual regression report',
      commitSha: readCliValue(args, '--commit-sha') || env.GITHUB_SHA?.slice(0, 12) || '',
      runUrl: readCliValue(args, '--run-url') || env.VISUAL_RUN_URL || '',
    },
  }
}

export async function main(args = process.argv.slice(2), env = process.env) {
  const summary = await compareVisualSnapshots(cliOptions(args, env))
  console.log(
    `Visual report: ${summary.totals.changed} changed, ${summary.totals.added} added, ${summary.totals.removed} removed, ${summary.totals.unchanged} unchanged.`
  )
  return summary
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error)
    process.exit(1)
  })
}
