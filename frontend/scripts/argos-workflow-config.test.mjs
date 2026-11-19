import { spawnSync } from 'node:child_process'
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
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
    expect(workflow).toContain('group: ${{ github.workflow }}-visual-state-')
    expect(workflow).toContain("&& 'baseline' || 'reports' }}")
    expect(workflow).toContain('cancel-in-progress: false')
    expect(workflow).toContain('push:')
    expect(workflow).toContain('frontend/src/**')
    expect(workflow).toContain('frontend/.storybook/**')
    expect(workflow).toContain('frontend/scripts/**')
    expect(workflow).toContain('visual-regression-state')
    expect(workflow).toContain('persist-credentials: false')
    expect(workflow).toContain('uses: ./source/.github/actions/install-playwright-chromium')
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
    expect(workflow).toContain(
      'gh run download "$SOURCE_RUN_ID" -R "$GITHUB_REPOSITORY" --name visual-actual'
    )
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
    // Default pull_request checkout is the merge ref, so snapshots show the PR on current main.
    expect(captureWorkflow).not.toMatch(/^\s+ref:/m)
    expect(captureWorkflow).toContain('npm run visual:screenshots')
    expect(captureWorkflow).toContain('actions/upload-artifact@v7')
    expect(captureWorkflow).toContain('name: visual-actual')
    // Shards upload visual-actual-N; only a run where every shard succeeded
    // merges them into the single artifact visual-regression.yml downloads.
    expect(captureWorkflow).toContain('STORYBOOK_SNAPSHOT_SHARD: ${{ matrix.shard }}/3')
    expect(captureWorkflow).toContain('name: visual-actual-${{ matrix.shard }}')
    expect(captureWorkflow).toContain('pattern: visual-actual-*')
    expect(captureWorkflow).toContain('needs: capture')
    // The merged upload, not a shard upload, must carry the exact name the
    // report workflow downloads, and it must refuse a partial set of shards.
    const mergeJob = captureWorkflow.slice(captureWorkflow.indexOf('\n  merge:\n'))
    expect(mergeJob).toMatch(/^\s+name: visual-actual$/m)
    expect(mergeJob).toContain('for shard in 1 2 3; do')
    expect(mergeJob).toContain('Re-run all jobs, not only the failed ones.')
    expect(captureWorkflow).not.toContain('actions: write')
    expect(captureWorkflow).not.toContain('pull-requests: write')
    expect(captureWorkflow).not.toContain('pages: write')

    expect(pagesWorkflow).toContain('visual-regression-state')
    expect(pagesWorkflow).toContain('docs/.vitepress/dist/visual')
  })

  it('merges snapshot shards only when every shard holds screenshots', async () => {
    const captureWorkflow = await readText('.github/workflows/visual-snapshot-capture.yml')
    const step = captureWorkflow.split('- name: Require every shard\n        run: |\n')[1]
    expect(step, 'Require every shard step not found').toBeDefined()
    // The run block is every line indented at least as far as its first line;
    // blank lines inside it belong to the script too.
    const lines = step.split('\n')
    const indent = lines.find((line) => line.trim()).match(/^ */)[0]
    const end = lines.findIndex((line) => line.trim() && !line.startsWith(indent))
    const script = lines
      .slice(0, end === -1 ? lines.length : end)
      .map((line) => line.slice(indent.length))
      .join('\n')

    const dirs = []
    async function runWithShards(filesByShard) {
      const dir = await mkdtemp(path.join(tmpdir(), 'visual-merge-'))
      dirs.push(dir)
      for (const [shard, files] of Object.entries(filesByShard)) {
        await mkdir(path.join(dir, 'shards', `visual-actual-${shard}`), { recursive: true })
        for (const file of files) {
          await writeFile(path.join(dir, 'shards', `visual-actual-${shard}`, file), 'x')
        }
      }
      const result = spawnSync('bash', ['-eo', 'pipefail', '-c', script], { cwd: dir })
      return { status: result.status, output: String(result.stdout), dir }
    }

    try {
      const complete = await runWithShards({ 1: ['a.png'], 2: ['b.png'], 3: ['c.png'] })
      expect(complete.status).toBe(0)
      expect((await readdir(path.join(complete.dir, 'visual-actual'))).sort()).toEqual([
        'a.png',
        'b.png',
        'c.png',
      ])

      // A shard directory without screenshots, or no directory at all, stops
      // the merge with the step's own exit 1.
      for (const shards of [
        { 1: ['a.png'], 2: ['b.png'], 3: ['meta.json'] },
        { 1: ['a.png'], 2: ['b.png'] },
      ]) {
        const partial = await runWithShards(shards)
        expect(partial.status).toBe(1)
        expect(partial.output).toContain('visual-actual-3 is missing. Re-run all jobs')
      }
    } finally {
      await Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true })))
    }
  })
})
