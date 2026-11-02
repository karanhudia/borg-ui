import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { translateBackendKey } from '../translateBackendKey'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe.each(['en', 'de', 'es', 'it'])('source preparation failures in %s', (language) => {
  it('renders the failed source cause', async () => {
    await i18n.changeLanguage(language)
    const message = translateBackendKey(
      JSON.stringify({
        key: 'backend.errors.service.failedPrepareSourcePathsDetails',
        params: { error: 'SSH connection for source.test not found' },
      })
    )
    expect(message).toContain('SSH connection for source.test not found')
    expect(message).not.toContain('{{')
    expect(message).not.toContain('backend.errors.')
  })

  it('still renders historical preparation failures without diagnostic params', async () => {
    await i18n.changeLanguage(language)
    const message = translateBackendKey(
      JSON.stringify({
        key: 'backend.errors.service.failedPrepareSourcePaths',
      })
    )
    expect(message).not.toContain('{{')
    expect(message).not.toContain('backend.errors.')
  })
})
