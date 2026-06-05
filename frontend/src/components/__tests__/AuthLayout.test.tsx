import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import AuthLayout from '../AuthLayout'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import { resetRemoteBackendStateForTests } from '../../services/remoteBackends/storage'

describe('AuthLayout', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
  })

  it('shows the backend target switcher in the auth shell', () => {
    renderWithProviders(
      <RemoteBackendProvider>
        <AuthLayout>
          <div>Login form</div>
        </AuthLayout>
      </RemoteBackendProvider>
    )

    expect(
      screen.getByRole('button', { name: /backend target local backend/i })
    ).toBeInTheDocument()
  })
})
