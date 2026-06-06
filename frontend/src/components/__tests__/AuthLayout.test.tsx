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

  it('leaves server selection to the login form content', () => {
    renderWithProviders(
      <RemoteBackendProvider>
        <AuthLayout>
          <div>Login form</div>
        </AuthLayout>
      </RemoteBackendProvider>
    )

    expect(
      screen.queryByRole('button', { name: /server target this server/i })
    ).not.toBeInTheDocument()
  })
})
