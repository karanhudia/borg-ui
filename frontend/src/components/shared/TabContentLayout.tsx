import { Box, Stack } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import type { ReactNode } from 'react'

interface TabContentLayoutProps {
  children: ReactNode
  /** Stable header area that stays outside tab body gates */
  header?: ReactNode
  /** Optional max width constraint; unconstrained by default */
  maxWidth?: number | string
  spacing?: number
  sx?: SxProps<Theme>
  contentSx?: SxProps<Theme>
}

const sxArray = (sx?: SxProps<Theme>) => (Array.isArray(sx) ? sx : sx ? [sx] : [])

export default function TabContentLayout({
  children,
  header,
  maxWidth,
  spacing = 3,
  sx,
  contentSx,
}: TabContentLayoutProps) {
  const rootSx = [{ ...(maxWidth ? { maxWidth, mx: 'auto' } : {}) }, ...sxArray(sx)]

  if (!header) {
    return <Box sx={rootSx}>{children}</Box>
  }

  return (
    <Box sx={rootSx}>
      <Stack spacing={spacing}>
        {header}
        <Box sx={contentSx}>{children}</Box>
      </Stack>
    </Box>
  )
}
