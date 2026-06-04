export const storyRootSelector = '#storybook-root'
export const storyRenderTimeoutMs = 120_000

export async function waitForStoryRoot(page) {
  await page.waitForSelector(storyRootSelector, {
    state: 'visible',
    timeout: storyRenderTimeoutMs,
  })
}
