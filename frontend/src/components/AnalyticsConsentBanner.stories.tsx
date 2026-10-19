import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import AnalyticsConsentBanner from './AnalyticsConsentBanner'

// The post-login analytics banner: title, message, toggle and actions. It no
// longer links to the retired public Umami dashboard.
const meta = {
  title: 'Components/AnalyticsConsentBanner',
  component: AnalyticsConsentBanner,
  args: {
    onConsentGiven: fn(),
  },
} satisfies Meta<typeof AnalyticsConsentBanner>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
