import { Box, ButtonBase, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { HardDrive } from 'lucide-react'
import { formatBytes } from '../../utils/dateUtils'
import { formatRetention } from '../../components/prune/formatRetention'
import { useT } from './tokens'
import type { SpaceSaving } from './types'

export function SpaceSavingsPanel({
  rows,
  onNavigate,
}: {
  rows: SpaceSaving[]
  onNavigate: (route: string) => void
}) {
  const T = useT()
  const { t } = useTranslation()
  if (rows.length === 0) return null
  return (
    <Box
      sx={{
        bgcolor: T.bgCard,
        border: `1px solid ${T.border}`,
        borderRadius: T.radius,
        p: 2.5,
        transition: 'border-color 0.2s',
        '&:hover': { borderColor: T.borderHover },
      }}
    >
      <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', mb: 0.5 }}>
        <HardDrive size={14} color={T.textMuted} />
        <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
          {t('dashboard.spaceSavings.title')}
        </Typography>
      </Stack>
      <Typography sx={{ fontSize: '0.75rem', color: T.textMuted, mb: 1.5 }}>
        {t('dashboard.spaceSavings.hint')}
      </Typography>
      <Stack spacing={1}>
        {rows.map((row) => (
          <ButtonBase
            key={row.repository_id}
            onClick={() =>
              onNavigate(
                `/repositories/${row.repository_id}/prune-preview?candidate=${row.candidate}`
              )
            }
            sx={{
              display: 'block',
              textAlign: 'left',
              width: '100%',
              border: `1px solid ${T.border}`,
              borderRadius: '8px',
              p: 1.25,
            }}
          >
            <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
              {row.repository_name}
            </Typography>
            <Typography sx={{ fontSize: '0.75rem', color: T.textMuted }}>
              {t('dashboard.spaceSavings.line', {
                size: formatBytes(row.freed_at_least),
                retention: formatRetention(row.retention),
              })}
              {row.stale ? ' ' : ''}
              {row.stale && (
                <Box component="span" sx={{ fontStyle: 'italic' }}>
                  {t('dashboard.spaceSavings.stale')}
                </Box>
              )}
            </Typography>
          </ButtonBase>
        ))}
      </Stack>
    </Box>
  )
}
