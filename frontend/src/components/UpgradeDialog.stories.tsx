import { useEffect } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Button, Typography } from '@mui/material'
import UpgradeDialog from './UpgradeDialog'
import PlanGate from './shared/PlanGate'
import { communitySystemInfo } from '../services/remoteBackends/planStoryFixtures'
import { closeUpgradeDialog, openUpgradeDialog, type UpgradeRequest } from '../utils/upgradeDialog'

/** Opens the dialog the way a lock would, so each story shows the card a user
 *  sees after the click. The theme toolbar switches light and dark. */
function Opened(request: UpgradeRequest) {
  useEffect(() => {
    openUpgradeDialog(request)
    // The store outlives the story: leave nothing open for the next one.
    return closeUpgradeDialog
  }, [request])
  return <UpgradeDialog />
}

/** A lock and the dialog it opens, starting closed. */
function ClickALockStory() {
  useEffect(() => {
    closeUpgradeDialog()
    return closeUpgradeDialog
  }, [])
  return (
    <Box sx={{ display: 'grid', gap: 1 }}>
      <Typography variant="body2" color="text.secondary">
        Click the locked button.
      </Typography>
      <PlanGate
        feature="alerting_monitoring"
        disabled
        surface="monitoring_reports"
        operation="run_check"
        label="Run check now"
      >
        <Button variant="outlined" disabled>
          Run check now
        </Button>
      </PlanGate>
      <UpgradeDialog />
    </Box>
  )
}

const meta = {
  title: 'Components/UpgradeDialog',
  component: Opened,
  parameters: { layout: 'centered', systemInfo: communitySystemInfo },
} satisfies Meta<typeof Opened>

export default meta

type Story = StoryObj<typeof meta>

export const DatabaseTab: Story = {
  args: { feature: 'database_discovery', surface: 'source_selection_dialog' },
}

export const ContainerTab: Story = {
  args: { feature: 'container_backups', surface: 'source_selection_dialog' },
}

export const BorgV2Switch: Story = {
  args: { feature: 'borg_v2', surface: 'repository_wizard' },
}

export const MonitoringRunCheck: Story = {
  args: { feature: 'alerting_monitoring', surface: 'monitoring_reports' },
}

export const ReportsSendNow: Story = {
  args: { feature: 'backup_reports', surface: 'monitoring_reports' },
}

export const PlanRunLocked: Story = {
  args: {
    feature: 'database_discovery',
    surface: 'backup_plan_card',
    message:
      'This plan uses database backups, which requires Pro. Edit it or upgrade to Pro to run it.',
  },
}

/** A Borg 2 backup, prune, compact or check refused after full access ended. */
export const BorgV2Refused: Story = {
  args: { feature: 'borg_v2', surface: 'api', refused: true },
}

/** The whole path: a greyed control that answers its click with the card. */
export const ClickALock: Story = {
  args: { feature: 'alerting_monitoring', surface: 'monitoring_reports' },
  render: () => <ClickALockStory />,
}
