import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RcloneRemoteDialog from '../RcloneRemoteDialog'
import { renderWithProviders } from '../../../test/test-utils'
import i18n from '../../../i18n'
import type { RcloneOAuthSession, RcloneProvider } from '../../../services/api'

vi.mock('../../shared/CodeEditor', () => ({ default: () => null }))

const provider: RcloneProvider = {
  type: 'drive',
  label: 'Google Drive',
  description: 'Cloud backup',
  auth_type: 'oauth_token',
  type_editable: false,
  config_template: { type: 'drive', token: '' },
  fields: [],
  oauth_mode: 'borg_ui',
  oauth_configured: true,
}

const pendingSession: RcloneOAuthSession = {
  session_id: 'polling-test',
  provider: 'drive',
  status: 'awaiting_callback',
  oauth_mode: 'borg_ui',
  config: null,
  error: null,
}

async function startPolling(errorSession: RcloneOAuthSession) {
  const onGetOAuthSession = vi.fn().mockResolvedValue(errorSession)
  renderWithProviders(
    <RcloneRemoteDialog
      open
      providers={[provider]}
      initialRemote={{
        name: 'cloud',
        provider: 'drive',
        config_source: 'managed',
        redacted_config: { type: 'drive', token: '' },
      }}
      onClose={() => {}}
      onCreate={() => {}}
      onStartOAuth={async () => pendingSession}
      onGetOAuthSession={onGetOAuthSession}
    />
  )
  await userEvent.click(
    screen.getByRole('button', { name: String(i18n.t('wizard.location.rcloneOAuthStartBorgUi')) })
  )
  await waitFor(() => expect(onGetOAuthSession).toHaveBeenCalledWith('polling-test'), {
    timeout: 3500,
  })
}

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('RcloneRemoteDialog authorization polling failures', () => {
  it('translates structured rejection details during German polling', async () => {
    await i18n.changeLanguage('de')
    await startPolling({
      ...pendingSession,
      status: 'failed',
      error: 'Legacy English fallback',
      error_detail: {
        key: 'backend.errors.rclone.oauthCodeExchangeRejected',
        params: { http_status: 400, provider_error: 'invalid_grant' },
      },
    })
    expect(
      screen.getByText(
        'Der Provider hat die Autorisierung abgelehnt (HTTP 400: invalid_grant). Prüfe die Provider-Einstellungen oder starte die Autorisierung erneut.'
      )
    ).toBeInTheDocument()
    expect(screen.queryByText('Legacy English fallback')).not.toBeInTheDocument()
  })

  it('retains legacy plaintext errors when structured details are absent', async () => {
    await i18n.changeLanguage('de')
    await startPolling({ ...pendingSession, status: 'failed', error: 'Legacy provider failure' })
    expect(screen.getByText('Legacy provider failure')).toBeInTheDocument()
  })
})
