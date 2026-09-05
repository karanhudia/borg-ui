import { useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import RunStatusIcon from './RunStatusIcon'

export interface RunChainOperation {
  id?: number | string
  kind: string
  status: string
  progress_current?: number | null
  progress_total?: number | null
  progress_message?: string | null
  followups?: RunChainOperation[]
}

interface RunChainRowProps {
  operation: RunChainOperation
  maxVisible?: number
  // `inline` wraps the chain on one line under a table row; `stacked` lists
  // it vertically under a run and collapses it when every step succeeded.
  layout?: 'inline' | 'stacked'
}

const SUCCEEDED = new Set(['completed', 'completed_with_warnings', 'skipped'])

function FollowupEntry({ followup }: { followup: RunChainOperation }) {
  const { t } = useTranslation()
  return (
    <Box
      data-testid="run-chain-followup"
      data-status={followup.status}
      sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}
    >
      <RunStatusIcon status={followup.status} size={12} />
      <Typography variant="caption">{t(`operations.kind.${followup.kind}`)}</Typography>
      {followup.status === 'running' &&
        followup.progress_current != null &&
        followup.progress_total != null && (
          <Typography variant="caption" color="text.secondary">
            {followup.progress_current}/{followup.progress_total}
          </Typography>
        )}
    </Box>
  )
}

export default function RunChainRow({
  operation,
  maxVisible = 3,
  layout = 'inline',
}: RunChainRowProps) {
  const { t } = useTranslation()
  const followups = operation.followups ?? []
  const allSucceeded = followups.every((followup) => SUCCEEDED.has(followup.status))
  const collapsible =
    layout === 'stacked' ? allSucceeded && followups.length > 0 : followups.length > maxVisible
  const [expanded, setExpanded] = useState(false)

  if (followups.length === 0) return null

  return (
    <Box sx={{ pl: layout === 'stacked' ? 0 : 3, mt: 0.5 }}>
      {collapsible && !expanded ? (
        <Typography
          variant="caption"
          color="text.secondary"
          onClick={() => setExpanded(true)}
          sx={{ cursor: 'pointer', textDecoration: 'underline' }}
        >
          {t('activity.followupsCollapsed', { count: followups.length })}
        </Typography>
      ) : (
        <Stack
          direction={layout === 'stacked' ? 'column' : 'row'}
          spacing={layout === 'stacked' ? 0.5 : 2}
          useFlexGap
          sx={{ flexWrap: 'wrap' }}
        >
          {followups.map((followup, index) => (
            <FollowupEntry key={followup.id ?? index} followup={followup} />
          ))}
        </Stack>
      )}
    </Box>
  )
}
