import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import PasskeyEnrollmentPrompt from './PasskeyEnrollmentPrompt'
import { AuthProvider } from '../hooks/useAuth'

// The post-login prompt. Use the Theme toolbar to check it in both modes:
// the benefit icons and the fingerprint take theme shades, not dark-only hues.
const meta = {
  title: 'Components/PasskeyEnrollmentPrompt',
  component: PasskeyEnrollmentPrompt,
  decorators: [
    (Story) => (
      <AuthProvider>
        <Story />
      </AuthProvider>
    ),
  ],
  args: {
    open: true,
    onSnooze: fn(),
    onIgnore: fn(),
    onSuccess: fn(),
  },
} satisfies Meta<typeof PasskeyEnrollmentPrompt>

export default meta

type Story = StoryObj<typeof meta>

export const Open: Story = {}

export const Closed: Story = {
  args: {
    open: false,
  },
  parameters: {
    docs: {
      description: {
        story:
          'The closed prompt state used by Layout when WebAuthn is unsupported or enrollment is otherwise ineligible. This story sets open to false; it does not simulate browser capability detection.',
      },
    },
  },
}
