import { Box, Typography, Link as MuiLink } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import CategoryToken from '../CategoryToken'
import { formatElapsedTime } from '../../utils/dateUtils'
import type { OperationItem } from '../../types/operations'

interface ForegroundLaneRowProps {
  operation: OperationItem
}

export default function ForegroundLaneRow({ operation }: ForegroundLaneRowProps) {
  const { t } = useTranslation()
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
      <CategoryToken category={operation.category} />
      <Typography variant="body2" component="span" fontWeight={600}>
        {operation.repository}
      </Typography>
      <Typography variant="body2" component="span">
        {t(`operations.kind.${operation.kind}`)}
        {operation.backup_plan_name
          ? ` (${t('operations.background.plan')}: ${operation.backup_plan_name})`
          : ''}
      </Typography>
      {operation.started_at && (
        <Typography variant="caption" color="text.secondary">
          {formatElapsedTime(operation.started_at)}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        {t('operations.background.holdsLane')}
      </Typography>
      <MuiLink
        component={RouterLink}
        to={`/activity?repository_id=${operation.repository_id}`}
        sx={{ ml: 'auto' }}
      >
        {t('operations.background.viewActivity')}
      </MuiLink>
    </Box>
  )
}
