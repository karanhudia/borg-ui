import { readFile } from 'node:fs/promises'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

const frontendRoot = process.cwd()
const repoRoot = path.resolve(frontendRoot, '..')

async function readText(relativePath) {
  try {
    return await readFile(path.join(repoRoot, relativePath), 'utf8')
  } catch {
    return ''
  }
}

describe('GitHub Pages visual regression workflow', () => {
  it('wires frontend scripts and CI to publish automatic visual reports on GitHub Pages', async () => {
    const packageJson = JSON.parse(await readFile(path.join(frontendRoot, 'package.json'), 'utf8'))
    const workflow = await readText('.github/workflows/visual-regression.yml')
    const captureWorkflow = await readText('.github/workflows/visual-snapshot-capture.yml')
    const pagesWorkflow = await readText('.github/workflows/pages.yml')

    expect(packageJson.devDependencies).not.toHaveProperty('@argos-ci/cli')
    expect(packageJson.scripts).toMatchObject({
      snapshots: 'npm run visual:screenshots',
      'visual:report': 'node scripts/visual-regression-report.mjs',
    })
    expect(packageJson.scripts['visual:screenshots']).toContain('npm run build-storybook')
    expect(packageJson.scripts['visual:screenshots']).toContain(
      'node scripts/generate-storybook-snapshots.mjs'
    )
    expect(packageJson.scripts['argos:ci']).toBeUndefined()
    expect(packageJson.scripts['argos:upload']).toBeUndefined()

    expect(workflow).toContain('name: GitHub Pages Visual Regression')
    expect(workflow).toContain('workflow_run:')
    expect(workflow).toContain('workflows: ["Capture Storybook Visual Snapshots"]')
    expect(workflow).toContain('pull_request_target:')
    expect(workflow).toContain('types: [closed]')
    expect(workflow).toContain("github.event.workflow_run.conclusion == 'success'")
    expect(workflow).not.toContain('run-visuals')
    expect(workflow).toContain('group: ${{ github.workflow }}-visual-state')
    expect(workflow).toContain('cancel-in-progress: false')
    expect(workflow).toContain('push:')
    expect(workflow).toContain('frontend/src/**')
    expect(workflow).toContain('frontend/.storybook/**')
    expect(workflow).toContain('frontend/scripts/**')
    expect(workflow).toContain('visual-regression-state')
    expect(workflow).toContain('persist-credentials: false')
    expect(workflow).toContain('npx playwright install --with-deps chromium')
    expect(workflow).toContain('npm run visual:screenshots')
    expect(workflow).toContain('npm run visual:report')
    expect(workflow).toContain('Resolve pull request changed files')
    expect(workflow).toContain('VISUAL_CHANGED_FILES_PATH')
    expect(workflow).toContain('VISUAL_UNRELATED_DIFF_THRESHOLD: "0.001"')
    expect(workflow).toContain('node scripts/visual-pr-description.mjs')
    expect(workflow).toContain('mode="cleanup"')
    expect(workflow).toContain(
      'rm -rf visual-state/visual/reports/pr-${{ steps.visual_mode.outputs.pr_number }}'
    )
    expect(workflow).toContain('id: deployment')
    expect(workflow).toContain('steps.deployment.outputs.page_url')
    expect(workflow).toContain('GITHUB_TOKEN: ${{ github.token }}')
    expect(workflow).toContain('pull-requests: write')
    expect(workflow).toContain('actions: read')
    expect(workflow).toContain('ref: main')
    expect(workflow).toContain('gh run download "$SOURCE_RUN_ID" -R "$GITHUB_REPOSITORY" --name visual-actual')
    expect(workflow).toContain('Refusing unexpected visual artifact files.')
    expect(workflow).toContain(
      'pr_details="$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}")"'
    )
    expect(workflow).toContain("SOURCE_HEAD_SHA: ${{ github.event.workflow_run.head_sha || '' }}")
    expect(workflow).toContain('"head=${source_owner}:${SOURCE_HEAD_BRANCH}"')
    expect(workflow).toContain('pr_head_sha="$(jq -r .head.sha <<<"$pr_details")"')
    expect(workflow).toContain('elif [ "$pr_head_sha" != "$SOURCE_HEAD_SHA" ]; then')
    expect(workflow).toContain('mode="skip"')
    expect(workflow).not.toContain('ARGOS_TOKEN')

    expect(captureWorkflow).toContain('name: Capture Storybook Visual Snapshots')
    expect(captureWorkflow).toContain('pull_request:')
    expect(captureWorkflow).toContain('types: [opened, synchronize, reopened]')
    expect(captureWorkflow).toContain('contents: read')
    expect(captureWorkflow).toContain('ref: ${{ github.event.pull_request.head.sha }}')
    expect(captureWorkflow).toContain('npm run visual:screenshots')
    expect(captureWorkflow).toContain('actions/upload-artifact@v4')
    expect(captureWorkflow).toContain('name: visual-actual')
    expect(captureWorkflow).not.toContain('pull-requests: write')
    expect(captureWorkflow).not.toContain('pages: write')

    expect(pagesWorkflow).toContain('visual-regression-state')
    expect(pagesWorkflow).toContain('docs/.vitepress/dist/visual')
  })
})
