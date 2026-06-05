import { Box, Stack, Tooltip, Typography } from '@mui/material'
import type { ReactNode } from 'react'

interface RichSelectRowProps {
  icon?: ReactNode
  iconFrame?: boolean
  primary: string
  secondary?: string
  indicator?: ReactNode
}

export default function RichSelectRow({
  icon,
  iconFrame = true,
  primary,
  secondary,
  indicator,
}: RichSelectRowProps) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, width: '100%', minWidth: 0 }}>
      {icon && (
        <Box
          sx={{
            width: 32,
            height: 32,
            borderRadius: iconFrame ? 1 : 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: iconFrame ? 'action.hover' : 'transparent',
            color: iconFrame ? 'text.secondary' : 'inherit',
            flexShrink: 0,
          }}
        >
          {icon}
        </Box>
      )}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
          <Tooltip title={primary} placement="top" enterDelay={500}>
            <Typography
              variant="body2"
              fontWeight={600}
              lineHeight={1.3}
              noWrap
              sx={{ minWidth: 0, flex: '1 1 auto' }}
            >
              {primary}
            </Typography>
          </Tooltip>
          {indicator}
        </Stack>
        {secondary && (
          <Tooltip title={secondary} placement="top" enterDelay={500}>
            <Typography
              variant="caption"
              color="text.secondary"
              lineHeight={1.3}
              noWrap
              sx={{ display: 'block', minWidth: 0 }}
            >
              {secondary}
            </Typography>
          </Tooltip>
        )}
      </Box>
    </Box>
  )
}
