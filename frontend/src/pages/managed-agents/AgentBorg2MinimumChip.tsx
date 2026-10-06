import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { agentChipSx } from './agentChipSx'
import { borg2MinimumParams, type BorgBinary } from './agentBorg2Minimum'

/**
 * Shown on an endpoint whose Borg 2 is older than the server's (#1306). The
 * server decides (`borg2_below_minimum`) and refuses every Borg 2 job for
 * such an endpoint; the chip says so before a job is tried.
 */
export default function AgentBorg2MinimumChip({
  belowMinimum,
  minimumVersion,
  borgVersions,
}: {
  belowMinimum?: boolean | null
  minimumVersion?: string | null
  borgVersions?: BorgBinary[] | null
}) {
  const { t } = useTranslation()

  if (!belowMinimum) return null

  return (
    <Tooltip
      title={t(
        'managedAgents.page.borg2Minimum.tooltip',
        borg2MinimumParams(borgVersions, minimumVersion)
      )}
      arrow
    >
      <Chip
        size="small"
        variant="outlined"
        color="error"
        label={t('managedAgents.page.borg2Minimum.label')}
        sx={agentChipSx}
      />
    </Tooltip>
  )
}
