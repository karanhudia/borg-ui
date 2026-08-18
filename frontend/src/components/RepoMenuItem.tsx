import { Box, Chip, Stack, Typography } from '@mui/material'
import { Database } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import BorgVersionChip from './BorgVersionChip'

interface RepoMenuItemProps {
  name: string
  path: string
  borgVersion?: number
  mode?: 'full' | 'observe'
  hasRunningMaintenance?: boolean
  maintenanceLabel?: string
  /** Hide the monospace path line (e.g. compact filter dropdowns) */
  hidePath?: boolean
}

const observeChipSx = {
  height: '16px',
  fontSize: '0.6rem',
  fontWeight: 600,
  bgcolor: 'info.main',
  color: '#fff',
  border: 'none',
  '& .MuiChip-label': { px: 0.6 },
} as const

export default function RepoMenuItem({
  name,
  path,
  borgVersion,
  mode,
  hasRunningMaintenance,
  maintenanceLabel = 'maintenance running',
  hidePath = false,
}: RepoMenuItemProps) {
  const { t } = useTranslation()
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{
        alignItems: 'center',
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      <Database size={16} style={{ flexShrink: 0 }} />
      <Box sx={{ minWidth: 0, overflow: 'hidden' }}>
        <Stack
          direction="row"
          spacing={0.75}
          sx={{
            alignItems: 'center',
          }}
        >
          <Typography
            variant="body2"
            sx={{
              fontWeight: 500,
            }}
          >
            {name}
          </Typography>
          <BorgVersionChip borgVersion={borgVersion} compact />
          {mode === 'observe' && (
            <Chip label={t('repositories.observeOnly')} size="small" sx={observeChipSx} />
          )}
          {hasRunningMaintenance && (
            <Typography
              component="span"
              variant="caption"
              sx={{
                color: 'warning.main',
              }}
            >
              {maintenanceLabel}
            </Typography>
          )}
        </Stack>
        {!hidePath && (
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,SFMono-Regular,monospace',
              display: 'block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {path}
          </Typography>
        )}
      </Box>
    </Stack>
  )
}
