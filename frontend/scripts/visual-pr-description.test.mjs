import { describe, expect, it } from 'vitest'

import {
  buildVisualRegressionSection,
  replaceVisualRegressionSection,
} from './visual-pr-description.mjs'

const summary = {
  totals: {
    changed: 2,
    added: 1,
    removed: 1,
    unchanged: 12,
    actual: 16,
    baseline: 15,
  },
  changed: [
    { fileName: 'components-button--default.png', diffRatio: 0.0123 },
    { fileName: 'pages-dashboard--desktop.png', diffRatio: 0.002 },
  ],
  added: [{ fileName: 'components-dialog--open.png' }],
  removed: [{ fileName: 'legacy-card--default.png' }],
}

describe('buildVisualRegressionSection', () => {
  it('summarizes changed, added, and removed screenshots with the report link', () => {
    const section = buildVisualRegressionSection({
      summary,
      reportUrl: 'https://docs.example.test/visual/reports/pr-42/',
      runUrl: 'https://github.example.test/actions/runs/99',
    })

    expect(section).toContain('<!-- visual-regression:start -->')
    expect(section).toContain('Visual regression report')
    expect(section).toContain('https://docs.example.test/visual/reports/pr-42/')
    expect(section).toContain('2 changed')
    expect(section).toContain('1 added')
    expect(section).toContain('1 removed')
    expect(section).toContain('components-button--default.png')
    expect(section).toContain('1.23%')
    expect(section).toContain('components-dialog--open.png')
    expect(section).toContain('legacy-card--default.png')
    expect(section).toContain('https://github.example.test/actions/runs/99')
  })

  it('renders a compact success state when no visual files changed', () => {
    const section = buildVisualRegressionSection({
      summary: {
        totals: { changed: 0, added: 0, removed: 0, unchanged: 4, actual: 4, baseline: 4 },
        changed: [],
        added: [],
        removed: [],
      },
      reportUrl: 'https://docs.example.test/visual/reports/pr-43/',
    })

    expect(section).toContain('No visual changes detected')
    expect(section).toContain('4 unchanged')
  })
})

describe('replaceVisualRegressionSection', () => {
  it('appends the visual section when the PR body has none', () => {
    const updated = replaceVisualRegressionSection('Original PR notes.', 'VISUAL SECTION')

    expect(updated).toBe('Original PR notes.\n\nVISUAL SECTION')
  })

  it('replaces the existing marked visual section without changing surrounding text', () => {
    const updated = replaceVisualRegressionSection(
      [
        'Before',
        '<!-- visual-regression:start -->',
        'Old section',
        '<!-- visual-regression:end -->',
        'After',
      ].join('\n'),
      'New section'
    )

    expect(updated).toBe(['Before', 'New section', 'After'].join('\n'))
  })
})
