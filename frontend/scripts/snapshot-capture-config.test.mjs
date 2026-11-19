import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  settleInBrowser,
  storyRenderTimeoutMs,
  storyReadySelectors,
  storyRootSelector,
  waitForStoryRoot,
  waitForStoryToSettle,
} from './snapshot-capture-config.mjs'

describe('waitForStoryRoot', () => {
  it('waits long enough for slow Storybook story chunks to render', async () => {
    const calls = []
    const page = {
      async waitForSelector(selector, options) {
        calls.push({ options, selector })
      },
    }

    await waitForStoryRoot(page)

    expect(storyRootSelector).toBe('#storybook-root')
    expect(storyReadySelectors).toEqual([
      '#storybook-root',
      '[role="dialog"]',
      '[role="alertdialog"]',
    ])
    expect(storyRenderTimeoutMs).toBe(120_000)
    expect(calls).toEqual([
      ...storyReadySelectors.map((selector) => ({
        selector,
        options: {
          state: 'visible',
          timeout: 120_000,
        },
      })),
    ])
  })
})

describe('settleInBrowser', () => {
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('waits until the DOM has been quiet, not just until it first renders', async () => {
    vi.useFakeTimers()
    let settled = false
    const settling = settleInBrowser({ quietMs: 250, maxMs: 3_000 }).then(() => {
      settled = true
    })

    // A late data fill, like a path suggested once a mocked request lands.
    await vi.advanceTimersByTimeAsync(200)
    document.body.textContent = '/home/backup/borg-backups/alex'
    await vi.advanceTimersByTimeAsync(200)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(100)
    await settling
    expect(settled).toBe(true)
  })

  it('gives up after the cap when a story never stops changing', async () => {
    vi.useFakeTimers()
    let settled = false
    const settling = settleInBrowser({ quietMs: 250, maxMs: 1_000 }).then(() => {
      settled = true
    })

    for (let tick = 0; tick < 9; tick += 1) {
      document.body.textContent = String(tick)
      await vi.advanceTimersByTimeAsync(100)
    }
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(100)
    await settling
    expect(settled).toBe(true)
  })
})

describe('waitForStoryToSettle', () => {
  const fakePage = (hasEditor) => {
    const calls = []
    return {
      calls,
      async $(selector) {
        calls.push(['$', selector])
        return hasEditor ? {} : null
      },
      async waitForSelector(selector, options) {
        calls.push(['waitForSelector', selector, options])
      },
      async evaluate() {
        calls.push(['evaluate'])
      },
      async waitForLoadState(state, options) {
        calls.push(['waitForLoadState', state, options])
      },
    }
  }

  it('waits for any code editor and its stylesheet, then settles again', async () => {
    const page = fakePage(true)
    await waitForStoryToSettle(page)
    expect(page.calls).toEqual([
      ['evaluate'],
      ['$', '[data-code-editor]'],
      ['waitForSelector', '[data-code-editor-loading]', { state: 'detached', timeout: 120_000 }],
      ['waitForLoadState', 'networkidle', { timeout: 120_000 }],
      ['evaluate'],
    ])
  })

  it('settles once when the story has no code editor', async () => {
    const page = fakePage(false)
    await waitForStoryToSettle(page)
    expect(page.calls).toEqual([['evaluate'], ['$', '[data-code-editor]']])
  })
})
