import { Box, Chip, Stack, Typography } from '@mui/material'
import { Database } from 'lucide-react'

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

const v2ChipSx = {
  height: '16px',
  fontSize: '0.6rem',
  fontWeight: 700,
  fontFamily: 'monospace',
  bgcolor: '#6366f1',
  color: '#fff',
  border: 'none',
  '& .MuiChip-label': { px: 0.6 },
} as const

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
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Database size={16} />
      <Box>
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Typography variant="body2" fontWeight={500}>
            {name}
          </Typography>
          {borgVersion === 2 && <Chip label="v2" size="small" sx={v2ChipSx} />}
          {mode === 'observe' && <Chip label="Observe Only" size="small" sx={observeChipSx} />}
          {hasRunningMaintenance && (
            <Typography component="span" variant="caption" color="warning.main">
              {maintenanceLabel}
            </Typography>
          )}
        </Stack>
        {!hidePath && (
          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
            {path}
          </Typography>
        )}
      </Box>
    </Stack>
  )
}
