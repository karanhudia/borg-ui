import { Box, Typography } from '@mui/material'

interface VersionChipProps {
  label: string
  version: string
  accent?: boolean
}

export default function VersionChip({ label, version, accent = false }: VersionChipProps) {
  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        px: 0.875,
        py: 0.25,
        borderRadius: '4px',
        bgcolor: accent
          ? (theme) =>
              theme.palette.mode === 'dark' ? 'rgba(99,102,241,0.12)' : 'rgba(99,102,241,0.08)'
          : 'action.hover',
        border: '1px solid',
        borderColor: accent
          ? (theme) =>
              theme.palette.mode === 'dark' ? 'rgba(99,102,241,0.3)' : 'rgba(99,102,241,0.25)'
          : 'divider',
      }}
    >
      <Typography
        sx={{
          fontSize: '0.6rem',
          fontWeight: 700,
          color: accent ? 'rgb(99,102,241)' : 'text.disabled',
          letterSpacing: '0.04em',
          lineHeight: 1,
        }}
      >
        {label}
      </Typography>
      <Typography
        sx={{
          fontSize: '0.6rem',
          fontWeight: 500,
          color: 'text.secondary',
          fontFamily: 'monospace',
          lineHeight: 1,
        }}
      >
        {version}
      </Typography>
    </Box>
  )
}
