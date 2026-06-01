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

describe('Argos visual regression workflow', () => {
  it('wires frontend scripts and CI to upload Storybook screenshots to Argos', async () => {
    const packageJson = JSON.parse(await readFile(path.join(frontendRoot, 'package.json'), 'utf8'))
    const workflow = await readText('.github/workflows/argos-visual-regression.yml')

    expect(packageJson.devDependencies).toHaveProperty('@argos-ci/cli')
    expect(packageJson.scripts).toMatchObject({
      snapshots: 'npm run argos:screenshots',
      'argos:ci': 'npm run argos:screenshots && npm run argos:upload',
    })
    expect(packageJson.scripts['argos:screenshots']).toContain('npm run build-storybook')
    expect(packageJson.scripts['argos:screenshots']).toContain(
      'node scripts/generate-storybook-snapshots.mjs'
    )
    expect(packageJson.scripts['argos:upload']).toBe('node scripts/upload-argos-snapshots.mjs')

    expect(workflow).toContain('name: Argos Visual Regression')
    expect(workflow).toContain('pull_request:')
    expect(workflow).toContain('push:')
    expect(workflow).toContain('frontend/src/**')
    expect(workflow).toContain('frontend/.storybook/**')
    expect(workflow).toContain('frontend/scripts/**')
    expect(workflow).toContain('persist-credentials: false')
    expect(workflow).toContain('npx playwright install --with-deps chromium')
    expect(workflow).toContain('npm run argos:ci')
    expect(workflow).toContain('GITHUB_TOKEN: ${{ github.token }}')
    expect(workflow).toContain('ARGOS_TOKEN: ${{ secrets.ARGOS_TOKEN }}')
  })
})
