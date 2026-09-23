import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import AccountProfileSection from './AccountProfileSection'

// Role, 2FA and passkey badges draw their text in theme palette shades, so
// they read on both the light and the dark card.
const meta = {
  title: 'Components/AccountProfileSection',
  component: AccountProfileSection,
  args: {
    canManageSystem: true,
    profileForm: { username: 'admin', email: 'admin@example.com', full_name: 'Example Admin' },
    deploymentForm: { deployment_type: 'individual', enterprise_name: '' },
    isSavingProfile: false,
    isSavingDeployment: false,
    onProfileFormChange: fn(),
    onDeploymentFormChange: fn(),
    onSaveProfile: fn(),
    onSaveDeployment: fn(),
    onOpenChangePassword: fn(),
    onOpenEditProfile: fn(),
    roleLabel: 'Admin',
    isAdmin: true,
    isOperator: false,
    createdAt: '2026-01-15T10:00:00Z',
    totpEnabled: true,
    passkeyCount: 2,
  },
} satisfies Meta<typeof AccountProfileSection>

export default meta

type Story = StoryObj<typeof meta>

export const AdminWithSecurityBadges: Story = {}

export const Operator: Story = {
  args: { roleLabel: 'Operator', isAdmin: false, isOperator: true, canManageSystem: false },
}
