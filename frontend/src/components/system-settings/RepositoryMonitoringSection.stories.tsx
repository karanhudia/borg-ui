import type { Meta, StoryObj } from '@storybook/react-vite'
import RepositoryMonitoringSection from './RepositoryMonitoringSection'

const noop = () => {}

const meta = {
  title: 'Components/SystemSettings/RepositoryMonitoringSection',
  component: RepositoryMonitoringSection,
  args: {
    statsRefreshInterval: 60,
    autoPrunePreview: true,
    maxConcurrentScheduledBackups: 2,
    maxConcurrentScheduledChecks: 4,
    dashboardBackupWarningDays: 3,
    dashboardBackupCriticalDays: 7,
    dashboardCheckWarningDays: 7,
    dashboardCheckCriticalDays: 30,
    dashboardCompactWarningDays: 30,
    dashboardCompactCriticalDays: 60,
    dashboardRestoreCheckWarningDays: 14,
    dashboardRestoreCheckCriticalDays: 30,
    dashboardObserveFreshnessWarningDays: 2,
    dashboardObserveFreshnessCriticalDays: 7,
    isRefreshingStats: false,
    setStatsRefreshInterval: noop,
    setAutoPrunePreview: noop,
    setMaxConcurrentScheduledBackups: noop,
    setMaxConcurrentScheduledChecks: noop,
    setDashboardBackupWarningDays: noop,
    setDashboardBackupCriticalDays: noop,
    setDashboardCheckWarningDays: noop,
    setDashboardCheckCriticalDays: noop,
    setDashboardCompactWarningDays: noop,
    setDashboardCompactCriticalDays: noop,
    setDashboardRestoreCheckWarningDays: noop,
    setDashboardRestoreCheckCriticalDays: noop,
    setDashboardObserveFreshnessWarningDays: noop,
    setDashboardObserveFreshnessCriticalDays: noop,
    onRefreshStats: noop,
  },
} satisfies Meta<typeof RepositoryMonitoringSection>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const AutomaticPrunePreviewsOff: Story = {
  args: { autoPrunePreview: false },
}
