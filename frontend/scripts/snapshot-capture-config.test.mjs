import { describe, expect, it } from 'vitest'

import {
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
