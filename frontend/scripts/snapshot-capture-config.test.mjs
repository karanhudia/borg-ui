import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  settleInBrowser,
  storyRenderTimeoutMs,
  storyReadySelectors,
  storyRootSelector,
  waitForStoryRoot,
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
