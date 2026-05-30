import { Box, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'

interface RichSelectRowProps {
  icon?: ReactNode
  primary: string
  secondary?: string
  indicator?: ReactNode
}

export default function RichSelectRow({ icon, primary, secondary, indicator }: RichSelectRowProps) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, width: '100%', minWidth: 0 }}>
      {icon && (
        <Box
          sx={{
            width: 32,
            height: 32,
            borderRadius: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: 'action.hover',
            color: 'text.secondary',
            flexShrink: 0,
          }}
        >
          {icon}
        </Box>
      )}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} lineHeight={1.3} noWrap>
            {primary}
          </Typography>
          {indicator}
        </Stack>
        {secondary && (
          <Typography
            variant="caption"
            color="text.secondary"
            lineHeight={1.3}
            noWrap
            sx={{ display: 'block' }}
          >
            {secondary}
          </Typography>
        )}
      </Box>
    </Box>
  )
}
