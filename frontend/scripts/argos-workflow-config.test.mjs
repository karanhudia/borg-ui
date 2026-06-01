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
    expect(workflow).toContain('pull_request:')
    expect(workflow).toContain('types: [opened, synchronize, reopened, closed]')
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
    expect(workflow).toContain('actions/deploy-pages@v4')
    expect(workflow).toContain('GITHUB_TOKEN: ${{ github.token }}')
    expect(workflow).toContain('pull-requests: write')
    expect(workflow).not.toContain('ARGOS_TOKEN')

    expect(pagesWorkflow).toContain('visual-regression-state')
    expect(pagesWorkflow).toContain('docs/.vitepress/dist/visual')
  })
})
