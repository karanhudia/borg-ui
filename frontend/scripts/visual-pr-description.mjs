#!/usr/bin/env node

import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

export const visualRegressionStartMarker = '<!-- visual-regression:start -->'
export const visualRegressionEndMarker = '<!-- visual-regression:end -->'

function percent(value) {
  if (!Number.isFinite(value)) {
    return '0.00%'
  }

  return `${(value * 100).toFixed(2)}%`
}

function listItems(items, formatter) {
  if (!items || items.length === 0) {
    return '- None'
  }

  return items.map(formatter).join('\n')
}

function total(summary, key) {
  return summary?.totals?.[key] ?? 0
}

export function buildVisualRegressionSection({ summary, reportUrl, runUrl = '' }) {
  const hasChanges =
    total(summary, 'changed') > 0 || total(summary, 'added') > 0 || total(summary, 'removed') > 0
  const status = hasChanges ? 'Visual changes detected' : 'No visual changes detected'

  return [
    visualRegressionStartMarker,
    '## Visual regression report',
    '',
    `${status}: ${total(summary, 'changed')} changed, ${total(summary, 'added')} added, ${total(summary, 'removed')} removed, ${total(summary, 'unchanged')} unchanged.`,
    '',
    `Report: ${reportUrl}`,
    runUrl ? `Workflow run: ${runUrl}` : '',
    '',
    '<details>',
    '<summary>Changed files</summary>',
    '',
    listItems(
      summary?.changed,
      (item) =>
        `- \`${item.fileName}\`${item.diffRatio === undefined ? '' : ` (${percent(item.diffRatio)})`}`
    ),
    '',
    '</details>',
    '',
    '<details>',
    '<summary>New screenshots</summary>',
    '',
    listItems(summary?.added, (item) => `- \`${item.fileName}\``),
    '',
    '</details>',
    '',
    '<details>',
    '<summary>Removed screenshots</summary>',
    '',
    listItems(summary?.removed, (item) => `- \`${item.fileName}\``),
    '',
    '</details>',
    visualRegressionEndMarker,
  ]
    .filter((line) => line !== '')
    .join('\n')
}

export function replaceVisualRegressionSection(body, section) {
  const existingBody = body || ''
  const markerPattern = new RegExp(
    `${visualRegressionStartMarker}[\\s\\S]*?${visualRegressionEndMarker}`
  )

  if (markerPattern.test(existingBody)) {
    return existingBody.replace(markerPattern, section)
  }

  return existingBody.trim() ? `${existingBody}\n\n${section}` : section
}

async function githubJson({ token, url, method = 'GET', body, fetcher = fetch }) {
  const response = await fetcher(url, {
    method,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(
      `GitHub API ${method} ${url} failed with ${response.status}: ${await response.text()}`
    )
  }

  return response.json()
}

function requiredEnv(env, name) {
  const value = env[name]

  if (!value) {
    throw new Error(`${name} is required.`)
  }

  return value
}

async function resolvePrNumber(env) {
  if (env.VISUAL_PR_NUMBER) {
    return env.VISUAL_PR_NUMBER
  }

  if (env.GITHUB_EVENT_PATH) {
    const event = JSON.parse(await readFile(env.GITHUB_EVENT_PATH, 'utf8'))
    if (event.pull_request?.number) {
      return String(event.pull_request.number)
    }
  }

  throw new Error('VISUAL_PR_NUMBER or a pull_request GITHUB_EVENT_PATH is required.')
}

export async function updateVisualPrDescription({ env = process.env, fetchImplementation } = {}) {
  const token = requiredEnv(env, 'GITHUB_TOKEN')
  const repository = requiredEnv(env, 'GITHUB_REPOSITORY')
  const summaryPath = requiredEnv(env, 'VISUAL_SUMMARY_PATH')
  const reportUrl = requiredEnv(env, 'VISUAL_REPORT_URL')
  const runUrl = env.VISUAL_RUN_URL || ''
  const prNumber = await resolvePrNumber(env)
  const apiUrl = `https://api.github.com/repos/${repository}/pulls/${prNumber}`
  const summary = JSON.parse(await readFile(summaryPath, 'utf8'))
  const fetcher = fetchImplementation || fetch
  const pullRequest = await githubJson({ token, url: apiUrl, fetcher })
  const nextBody = replaceVisualRegressionSection(
    pullRequest.body || '',
    buildVisualRegressionSection({ summary, reportUrl, runUrl })
  )

  await githubJson({
    token,
    url: apiUrl,
    method: 'PATCH',
    fetcher,
    body: {
      body: nextBody,
    },
  })

  return nextBody
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  updateVisualPrDescription().catch((error) => {
    console.error(error)
    process.exit(1)
  })
}
