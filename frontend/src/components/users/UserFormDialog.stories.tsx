import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import { UserFormDialog } from './UserDialogs'

const meta: Meta<typeof UserFormDialog> = {
  title: 'Settings/UserFormDialog',
  component: UserFormDialog,
  args: {
    open: true,
    editingUser: null,
    userOidcFieldsExposed: false,
    onUserFormChange: fn(),
    onClose: fn(),
    onSubmit: fn(),
  },
}
export default meta
type Story = StoryObj<typeof UserFormDialog>

export const Empty: Story = {
  args: {
    userForm: {
      username: '',
      email: '',
      password: '',
      role: 'viewer',
      full_name: '',
      auth_source: 'local',
      oidc_subject: '',
    },
  },
}

/** Opened from an MCP hand-off link: everything but the password filled in. */
export const PrefilledFromLink: Story = {
  args: {
    userForm: {
      username: 'robin',
      email: 'robin@example.invalid',
      password: '',
      role: 'operator',
      full_name: 'Robin Example',
      auth_source: 'local',
      oidc_subject: '',
    },
  },
}
