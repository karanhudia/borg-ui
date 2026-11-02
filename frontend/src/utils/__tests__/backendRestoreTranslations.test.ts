import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { translateBackendKey } from '../translateBackendKey'

const failures = [
  'restoreFailedZeroFiles',
  'restoreFailedZeroFilesPermission',
  'restoreFailedZeroFilesPathNotFound',
  'restoreFailedExitCode',
  'restoreFailed',
]

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe.each(['en', 'de', 'es', 'it'])('restore failure diagnostics in %s', (language) => {
  it.each(failures)('renders the causal hint for %s', async (failure) => {
    await i18n.changeLanguage(language)
    const message = translateBackendKey(
      JSON.stringify({
        key: `backend.errors.service.${failure}Details`,
        params: { exitCode: 105, error: 'Cannot write /restore/file: permission denied' },
      })
    )
    expect(message).toContain('Cannot write /restore/file: permission denied')
    expect(message).not.toContain('{{')
    expect(message).not.toContain('backend.errors.')
  })

  it('still renders historical errors that have no diagnostic parameter', async () => {
    await i18n.changeLanguage(language)
    const message = translateBackendKey(
      JSON.stringify({
        key: 'backend.errors.service.restoreFailedZeroFilesPermission',
        params: { exitCode: 105 },
      })
    )
    expect(message).toContain('105')
    expect(message).not.toContain('{{')
    expect(message).not.toContain('backend.errors.')
  })
})
