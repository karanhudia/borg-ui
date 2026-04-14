import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen, fireEvent, userEvent } from '../../test/test-utils'
import AccountProfileSection from '../AccountProfileSection'
import AccountPasswordDialog from '../AccountPasswordDialog'
import AccountAccessSection from '../AccountAccessSection'
import AccountSecuritySection from '../AccountSecuritySection'
import AccountSecuritySettingsSection from '../AccountSecuritySettingsSection'
import AccountTabHeader from '../AccountTabHeader'
import AccountTabNavigation from '../AccountTabNavigation'

vi.mock('../ApiTokensSection', () => ({
  default: () => <div>API tokens section</div>,
}))

vi.mock('../UserPermissionsPanel', () => ({
  default: ({ title, subtitle }: { title: string; subtitle: string }) => (
    <div>
      <div>{title}</div>
      <div>{subtitle}</div>
    </div>
  ),
}))

describe('AccountProfileSection', () => {
  it('renders the password and edit profile cards when setup is incomplete', async () => {
    const user = userEvent.setup()
    const onOpenEditProfile = vi.fn()

    renderWithProviders(
      <AccountProfileSection
        canManageSystem={false}
        mustChangePassword={true}
        profileForm={{ username: 'admin', email: 'admin@example.com', full_name: 'Admin User' }}
        deploymentForm={{ deployment_type: 'individual', enterprise_name: '' }}
        isSavingProfile={false}
        isSavingDeployment={false}
        onProfileFormChange={vi.fn()}
        onDeploymentFormChange={vi.fn()}
        onSaveProfile={vi.fn()}
        onSaveDeployment={vi.fn()}
        onOpenChangePassword={vi.fn()}
        onOpenEditProfile={onOpenEditProfile}
      />
    )

    const headings = screen.getAllByText('Account password')
    expect(headings[0]).toBeInTheDocument()
    expect(screen.getByText('Password update required')).toBeInTheDocument()
    expect(screen.getByText('Edit profile')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /edit profile/i }))
    expect(onOpenEditProfile).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Deployment profile')).not.toBeInTheDocument()
  })

  it('drives deployment profile interactions and blocks enterprise save without organization name', async () => {
    const user = userEvent.setup()
    const onDeploymentFormChange = vi.fn()
    const onSaveDeployment = vi.fn()

    const { unmount } = renderWithProviders(
      <AccountProfileSection
        canManageSystem={true}
        mustChangePassword={false}
        profileForm={{ username: 'admin', email: 'admin@example.com', full_name: 'Admin User' }}
        deploymentForm={{ deployment_type: 'enterprise', enterprise_name: '' }}
        isSavingProfile={false}
        isSavingDeployment={false}
        onProfileFormChange={vi.fn()}
        onDeploymentFormChange={onDeploymentFormChange}
        onSaveProfile={vi.fn()}
        onSaveDeployment={onSaveDeployment}
        onOpenChangePassword={vi.fn()}
        onOpenEditProfile={vi.fn()}
      />
    )

    expect(screen.getByText('Deployment profile')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /save deployment/i })).toBeDisabled()

    await user.click(screen.getByText('Individual'))
    expect(onDeploymentFormChange).toHaveBeenCalledWith({ deployment_type: 'individual' })

    fireEvent.change(screen.getByLabelText(/organization name/i), {
      target: { value: 'NullCode AI' },
    })
    expect(onDeploymentFormChange).toHaveBeenCalledWith({ enterprise_name: 'NullCode AI' })

    unmount()

    renderWithProviders(
      <AccountProfileSection
        canManageSystem={true}
        mustChangePassword={false}
        profileForm={{ username: 'admin', email: 'admin@example.com', full_name: 'Admin User' }}
        deploymentForm={{ deployment_type: 'enterprise', enterprise_name: 'NullCode AI' }}
        isSavingProfile={false}
        isSavingDeployment={false}
        onProfileFormChange={vi.fn()}
        onDeploymentFormChange={onDeploymentFormChange}
        onSaveProfile={vi.fn()}
        onSaveDeployment={onSaveDeployment}
        onOpenChangePassword={vi.fn()}
        onOpenEditProfile={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /save deployment/i }))
    expect(onSaveDeployment).toHaveBeenCalledTimes(1)
  })
})

describe('AccountPasswordDialog', () => {
  it('shows mismatch feedback and supports cancel for optional password changes', async () => {
    const user = userEvent.setup()
    const onFormChange = vi.fn()
    const onSubmit = vi.fn()
    const onClose = vi.fn()

    renderWithProviders(
      <AccountPasswordDialog
        open={true}
        mustChangePassword={false}
        currentPassword="old-pass"
        newPassword="new-pass"
        confirmPassword="different-pass"
        isSubmitting={false}
        onClose={onClose}
        onFormChange={onFormChange}
        onSubmit={onSubmit}
      />
    )

    expect(screen.getByText('Passwords do not match')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalledWith('closeButton')

    fireEvent.submit(screen.getByRole('button', { name: /update password/i }).closest('form')!)
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('hides cancel when password change is mandatory', () => {
    renderWithProviders(
      <AccountPasswordDialog
        open={true}
        mustChangePassword={true}
        currentPassword=""
        newPassword=""
        confirmPassword=""
        isSubmitting={false}
        onClose={vi.fn()}
        onFormChange={vi.fn()}
        onSubmit={vi.fn()}
      />
    )

    expect(screen.getByText('Complete account setup')).toBeInTheDocument()
    expect(
      screen.getByText(
        /your password must be changed before you can navigate outside account settings/i
      )
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument()
  })
})

describe('AccountAccessSection', () => {
  it('shows repository permissions panel when the user lacks global repository access', () => {
    renderWithProviders(<AccountAccessSection hasGlobalRepositoryAccess={false} />)

    expect(screen.getByText('API tokens section')).toBeInTheDocument()
    expect(screen.getByText('Repository permissions')).toBeInTheDocument()
    expect(screen.getByText('Your current repository-level access.')).toBeInTheDocument()
  })

  it('shows the global access banner for admin-style access', () => {
    renderWithProviders(<AccountAccessSection hasGlobalRepositoryAccess={true} />)

    expect(screen.getByText('Global access')).toBeInTheDocument()
    expect(
      screen.getByText('Admin accounts inherit full access to all repositories and settings.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Repository permissions')).not.toBeInTheDocument()
  })
})

describe('AccountSecuritySection', () => {
  it('changes copy for mandatory password updates and opens the password dialog on click', async () => {
    const user = userEvent.setup()
    const onOpenChangePassword = vi.fn()

    renderWithProviders(
      <AccountSecuritySection
        mustChangePassword={true}
        onOpenChangePassword={onOpenChangePassword}
      />
    )

    expect(screen.getByText('Password update required')).toBeInTheDocument()
    await user.click(screen.getByText('Password update required'))
    expect(onOpenChangePassword).toHaveBeenCalledTimes(1)
  })
})

describe('AccountTabHeader', () => {
  it('renders identity chips and member metadata', () => {
    renderWithProviders(
      <AccountTabHeader
        username="admin"
        roleLabel="Administrator"
        roleColor="secondary"
        createdAt="2024-01-15T00:00:00Z"
      />
    )

    expect(screen.getByText('User Settings')).toBeInTheDocument()
    expect(screen.getByText('Administrator')).toBeInTheDocument()
    expect(screen.getByText(/@admin · since/i)).toBeInTheDocument()
  })
})

describe('AccountTabNavigation', () => {
  it('maps tab clicks to account views', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    renderWithProviders(<AccountTabNavigation value="profile" onChange={onChange} />)

    expect(screen.getByRole('tab', { name: /security/i })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /access/i }))

    expect(onChange).toHaveBeenCalledWith('access')
  })

  it('hides the security tab when account security is not applicable', () => {
    renderWithProviders(
      <AccountTabNavigation value="profile" onChange={vi.fn()} showSecurityTab={false} />
    )

    expect(screen.queryByRole('tab', { name: /security/i })).not.toBeInTheDocument()
  })
})

describe('AccountSecuritySettingsSection', () => {
  it('renders a dedicated security surface with TOTP and passkey summaries', () => {
    renderWithProviders(
      <AccountSecuritySettingsSection
        totpEnabled={false}
        recoveryCodesRemaining={0}
        totpLoading={false}
        onEnableTotp={vi.fn()}
        onDisableTotp={vi.fn()}
        passkeys={[]}
        passkeysLoading={false}
        onAddPasskey={vi.fn()}
        onDeletePasskey={vi.fn()}
      />
    )

    expect(screen.getByText('Security')).toBeInTheDocument()
    expect(screen.getAllByText('Two-factor authentication')).toHaveLength(2)
    expect(screen.getAllByText('Passkeys')).toHaveLength(2)
    expect(screen.getByText('Account security')).toBeInTheDocument()
  })
})
