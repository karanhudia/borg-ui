import { Chip } from '@mui/material'

interface BorgVersionChipProps {
  borgVersion: number | undefined
  /** Use compact sizing for dense contexts like dropdown menus */
  compact?: boolean
}

export default function BorgVersionChip({ borgVersion, compact = false }: BorgVersionChipProps) {
  if (borgVersion !== 2) return null

  return (
    <Chip
      label="v2"
      size="small"
      sx={{
        height: compact ? '16px' : '18px',
        fontSize: compact ? '0.6rem' : '0.65rem',
        fontWeight: 700,
        fontFamily: 'monospace',
        bgcolor: '#4f46e5', // Indigo 600: white text clears 4.5:1
        color: '#fff',
        border: 'none',
        letterSpacing: 0.5,
        '& .MuiChip-label': { px: compact ? 0.6 : 0.75 },
      }}
    />
  )
}
