import { useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { Check, XCircle, Loader2, AlertTriangle, Circle, MinusCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

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
}

const STATUS_ICON: Record<string, typeof Check> = {
  completed: Check,
  completed_with_warnings: Check,
  running: Loader2,
  queued: Circle,
  failed: XCircle,
  cancelled: XCircle,
  skipped: MinusCircle,
}

function FollowupEntry({ followup }: { followup: RunChainOperation }) {
  const { t } = useTranslation()
  const Icon = STATUS_ICON[followup.status] ?? AlertTriangle
  return (
    <Box
      data-testid="run-chain-followup"
      data-status={followup.status}
      sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
    >
      <Icon size={12} className={followup.status === 'running' ? 'animate-spin' : undefined} />
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

export default function RunChainRow({ operation, maxVisible = 3 }: RunChainRowProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const followups = operation.followups ?? []

  if (followups.length === 0) return null

  const collapsible = followups.length > maxVisible

  return (
    <Box sx={{ pl: 3, mt: 0.5 }}>
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
        <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap' }}>
          {followups.map((followup, index) => (
            <FollowupEntry key={followup.id ?? index} followup={followup} />
          ))}
        </Stack>
      )}
    </Box>
  )
}
