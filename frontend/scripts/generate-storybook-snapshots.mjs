import { createReadStream, existsSync } from 'node:fs'
import { mkdir, readFile, readdir, rm, stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

process.env.PLAYWRIGHT_BROWSERS_PATH ||= '0'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(__dirname, '..')
const staticDir = path.join(frontendRoot, 'storybook-static')
const indexPath = path.join(staticDir, 'index.json')
const snapshotsDir = path.join(frontendRoot, 'storybook-snapshots')
const localHostLibRoot = path.join(frontendRoot, '.playwright-host-libs', 'root')
const fixedNowIso = '2026-05-16T12:00:00.000Z'

function prependLocalHostLibraries() {
  const localLibraryDirs = [
    path.join(localHostLibRoot, 'usr', 'lib', 'aarch64-linux-gnu'),
    path.join(localHostLibRoot, 'usr', 'lib', 'x86_64-linux-gnu'),
    path.join(localHostLibRoot, 'usr', 'lib'),
  ].filter((libraryDir) => existsSync(libraryDir))

  if (localLibraryDirs.length === 0) {
    return
  }

  const existingLibraryPath = process.env.LD_LIBRARY_PATH
    ? process.env.LD_LIBRARY_PATH.split(path.delimiter)
    : []

  process.env.LD_LIBRARY_PATH = [...localLibraryDirs, ...existingLibraryPath].join(path.delimiter)

  const localFontsDir = path.join(localHostLibRoot, 'etc', 'fonts')
  if (!process.env.FONTCONFIG_PATH && existsSync(localFontsDir)) {
    process.env.FONTCONFIG_PATH = localFontsDir
  }
}

function getContentType(filePath) {
  const extension = path.extname(filePath)
  const types = {
    '.css': 'text/css',
    '.html': 'text/html',
    '.ico': 'image/x-icon',
    '.js': 'text/javascript',
    '.json': 'application/json',
    '.map': 'application/json',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.txt': 'text/plain',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  }

  return types[extension] || 'application/octet-stream'
}

async function fileExists(filePath) {
  try {
    await stat(filePath)
    return true
  } catch {
    return false
  }
}

function startStaticServer(rootDir) {
  const server = createServer(async (request, response) => {
    try {
      const requestUrl = new URL(request.url || '/', 'http://127.0.0.1')
      const pathname = requestUrl.pathname === '/' ? '/index.html' : requestUrl.pathname
      const normalizedPath = path.normalize(decodeURIComponent(pathname)).replace(/^(\.\.[/\\])+/, '')
      let filePath = path.join(rootDir, normalizedPath)
      const rootWithSeparator = `${rootDir}${path.sep}`

      if (filePath !== rootDir && !filePath.startsWith(rootWithSeparator)) {
        response.writeHead(403)
        response.end('Forbidden')
        return
      }

      const fileStat = await stat(filePath)
      if (fileStat.isDirectory()) {
        filePath = path.join(filePath, 'index.html')
      }

      response.writeHead(200, { 'Content-Type': getContentType(filePath) })
      createReadStream(filePath).pipe(response)
    } catch {
      response.writeHead(404)
      response.end('Not found')
    }
  })

  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (!address || typeof address === 'string') {
        reject(new Error('Unable to determine Storybook snapshot server address.'))
        return
      }

      resolve({
        server,
        baseUrl: `http://127.0.0.1:${address.port}`,
      })
    })
  })
}

async function readStoryEntries() {
  if (!(await fileExists(indexPath))) {
    throw new Error(`Storybook build not found at ${indexPath}. Run \`npm run build-storybook\` first.`)
  }

  const storybookIndex = JSON.parse(await readFile(indexPath, 'utf8'))
  const entries = Object.values(storybookIndex.entries || storybookIndex.stories || {})
  const stories = entries
    .filter((entry) => entry && entry.type === 'story' && entry.id)
    .sort((a, b) => a.id.localeCompare(b.id))

  if (stories.length === 0) {
    throw new Error('No Storybook story entries were found in storybook-static/index.json.')
  }

  return stories
}

async function removeStaleSnapshots(expectedFiles) {
  await mkdir(snapshotsDir, { recursive: true })
  const existingFiles = await readdir(snapshotsDir).catch(() => [])

  await Promise.all(
    existingFiles
      .filter((fileName) => fileName.endsWith('.png') && !expectedFiles.has(fileName))
      .map((fileName) => rm(path.join(snapshotsDir, fileName)))
  )
}

async function withFixedDate(page) {
  await page.addInitScript((isoDate) => {
    const RealDate = Date

    function FixedDate(...args) {
      if (!(this instanceof FixedDate)) {
        return RealDate()
      }

      return args.length === 0 ? new RealDate(isoDate) : new RealDate(...args)
    }

    FixedDate.UTC = RealDate.UTC
    FixedDate.parse = RealDate.parse
    FixedDate.now = () => new RealDate(isoDate).getTime()
    FixedDate.prototype = RealDate.prototype
    window.Date = FixedDate
  }, fixedNowIso)
}

async function captureStorySnapshots(stories, baseUrl) {
  let browser

  try {
    const { chromium } = await import('playwright')
    browser = await chromium.launch()
  } catch (error) {
    throw new Error(
      `Unable to launch Playwright Chromium. Run \`PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium\` and retry. Original error: ${
        error instanceof Error ? error.message : String(error)
      }`
    )
  }

  try {
    const context = await browser.newContext({
      deviceScaleFactor: 1,
      locale: 'en-US',
      timezoneId: 'UTC',
      viewport: { width: 720, height: 520 },
    })

    for (const story of stories) {
      const page = await context.newPage()
      const outputPath = path.join(snapshotsDir, `${story.id}.png`)

      await withFixedDate(page)
      await page.goto(`${baseUrl}/iframe.html?id=${encodeURIComponent(story.id)}&viewMode=story`, {
        waitUntil: 'networkidle',
      })
      await page.waitForSelector('#storybook-root', { state: 'visible' })
      await page.addStyleTag({
        content: `
          *, *::before, *::after {
            animation: none !important;
            caret-color: transparent !important;
            transition-duration: 0s !important;
            transition-property: none !important;
          }
        `,
      })
      await page.locator('#storybook-root').screenshot({ path: outputPath })
      await page.close()
      console.log(`Wrote ${path.relative(frontendRoot, outputPath)}`)
    }

    await context.close()
  } finally {
    await browser.close()
  }
}

async function main() {
  prependLocalHostLibraries()

  const stories = await readStoryEntries()
  const expectedFiles = new Set(stories.map((story) => `${story.id}.png`))
  await removeStaleSnapshots(expectedFiles)

  const { server, baseUrl } = await startStaticServer(staticDir)

  try {
    await captureStorySnapshots(stories, baseUrl)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
})
