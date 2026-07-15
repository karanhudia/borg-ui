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
