import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { renderWithProviders, screen } from '../../../test/test-utils'
import QuickStartCustomize from '../QuickStartCustomize'
import { createInitialQuickStartAnswers } from '../quickStartState'

function answersWith(
  settings: Partial<ReturnType<typeof createInitialQuickStartAnswers>['settings']>
) {
  const answers = createInitialQuickStartAnswers()
  return { ...answers, settings: { ...answers.settings, ...settings } }
}

describe('QuickStartCustomize', () => {
  it('offers the encryption switch for Borg 1', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <QuickStartCustomize
        answers={answersWith({ borgVersion: 1 })}
        onSettingsChange={vi.fn()}
        canUseBorg2
      />
    )

    await user.click(screen.getByRole('button', { name: /customi[sz]e/i }))

    expect(screen.getByRole('switch', { name: /encrypt/i })).toBeInTheDocument()
  })

  it('has no encryption switch for Borg 2, which has no unencrypted mode', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <QuickStartCustomize
        answers={answersWith({ borgVersion: 2, encryption: 'repokey-aes-ocb' })}
        onSettingsChange={vi.fn()}
        canUseBorg2
      />
    )

    await user.click(screen.getByRole('button', { name: /customi[sz]e/i }))

    expect(screen.queryByRole('switch', { name: /encrypt/i })).not.toBeInTheDocument()
  })

  it('turns encryption on when an unencrypted setup moves to Borg 2', async () => {
    const user = userEvent.setup()
    const onSettingsChange = vi.fn()
    renderWithProviders(
      <QuickStartCustomize
        answers={answersWith({ borgVersion: 1, encryption: 'none' })}
        onSettingsChange={onSettingsChange}
        canUseBorg2
      />
    )

    await user.click(screen.getByRole('button', { name: /customi[sz]e/i }))
    await user.click(screen.getByRole('button', { name: 'Borg 2' }))

    expect(onSettingsChange).toHaveBeenCalledWith({
      borgVersion: 2,
      encryption: 'repokey-aes-ocb',
    })
  })
})
