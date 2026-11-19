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

// CodeEditor pulls Monaco from a CDN, so how long it shows its loading box
// depends on the network. Wait it out, or the shot is a coin flip.
export const codeEditorSelector = '[data-code-editor]'
export const pendingContentSelector = '[data-code-editor-loading]'

export async function waitForStoryToSettle(page) {
  const settle = () =>
    page.evaluate(settleInBrowser, {
      quietMs: storySettleQuietMs,
      maxMs: storySettleMaxMs,
    })
  await settle()
  // Editors only mount after the story renders, so check after settling. Key on
  // the editor, not its loading box: Monaco can finish inside the first settle
  // while its stylesheet is still in flight.
  if (await page.$(codeEditorSelector)) {
    await page.waitForSelector(pendingContentSelector, {
      state: 'detached',
      timeout: storyRenderTimeoutMs,
    })
    // Monaco's stylesheet comes from the CDN too and can land after the editor mounts.
    await page.waitForLoadState('networkidle', { timeout: storyRenderTimeoutMs })
    await settle()
  }
}
