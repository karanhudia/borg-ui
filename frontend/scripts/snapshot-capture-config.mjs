export const storyRootSelector = '#storybook-root'
export const storyReadySelectors = [storyRootSelector, '[role="dialog"]', '[role="alertdialog"]']
export const storyRenderTimeoutMs = 120_000

export async function waitForStoryRoot(page) {
  const waiters = storyReadySelectors.map((selector) =>
    page.waitForSelector(selector, {
      state: 'visible',
      timeout: storyRenderTimeoutMs,
    })
  )

  try {
    await Promise.any(waiters)
  } catch (error) {
    if (error instanceof AggregateError && error.errors.length > 0) {
      throw error.errors[0]
    }
    throw error
  }
}

// Stories that load mocked data fill in after the root appears, so a shot taken
// right away catches them half rendered at random. Wait for the DOM to go quiet.
export const storySettleQuietMs = 250
export const storySettleMaxMs = 3_000

// Runs in the page, so it must not close over anything in this module.
export function settleInBrowser({ quietMs, maxMs }) {
  return new Promise((resolve) => {
    let quietTimer
    const done = () => {
      observer.disconnect()
      clearTimeout(quietTimer)
      clearTimeout(maxTimer)
      resolve()
    }
    const restartQuiet = () => {
      clearTimeout(quietTimer)
      quietTimer = setTimeout(done, quietMs)
    }
    const observer = new MutationObserver(restartQuiet)
    observer.observe(document.body, {
      attributes: true,
      characterData: true,
      childList: true,
      subtree: true,
    })
    const maxTimer = setTimeout(done, maxMs)
    restartQuiet()
  })
}

export async function waitForStoryToSettle(page) {
  await page.evaluate(settleInBrowser, {
    quietMs: storySettleQuietMs,
    maxMs: storySettleMaxMs,
  })
}
