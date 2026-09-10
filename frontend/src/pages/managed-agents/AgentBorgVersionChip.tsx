import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { agentChipSx } from './agentChipSx'

/**
 * Whether the Borg major version an endpoint is pinned to has actually landed.
 *
 * The rule is the same one `borg_pin_satisfied` applies in
 * `app/core/agent_versions.py`, which decides when a requested upgrade is
 * resolved. It is duplicated rather than sent as a computed field because the
 * response already carries both halves, and the two must be changed together.
 *
 * Renders nothing without a pin. An endpoint that tracks whatever is installed
 * has nothing to compare against, and the card's stats row already lists the
 * Borg binaries it reports.
 */
export default function AgentBorgVersionChip({
  desiredBorgVersion,
  borgVersions,
}: {
  desiredBorgVersion?: string | null
  borgVersions?: Array<Record<string, unknown>> | null
}) {
  const { t } = useTranslation()

  if (!desiredBorgVersion) return null

  // The agent reports `major` as a number and the pin is stored as a string,
  // so compare as strings. Entries arrive from a heartbeat, so an entry that
  // is not an object simply does not match rather than throwing.
  const satisfied = (borgVersions ?? []).some(
    (binary) =>
      Boolean(binary) &&
      binary.major !== undefined &&
      binary.major !== null &&
      String(binary.major) === String(desiredBorgVersion)
  )

  const label = satisfied
    ? t('managedAgents.page.borgPin.active', { version: desiredBorgVersion })
    : t('managedAgents.page.borgPin.pending', { version: desiredBorgVersion })
  const tooltip = satisfied
    ? t('managedAgents.page.borgPin.activeTooltip', { version: desiredBorgVersion })
    : t('managedAgents.page.borgPin.pendingTooltip', { version: desiredBorgVersion })

  return (
    <Tooltip title={tooltip} arrow>
      <Chip
        size="small"
        variant="outlined"
        color={satisfied ? 'info' : 'warning'}
        label={label}
        sx={agentChipSx}
      />
    </Tooltip>
  )
}
