import { Card, CardContent } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import type { ReactNode } from 'react'

interface SettingsCardProps {
  children: ReactNode
  /** Card-level overrides — e.g. overflow, maxWidth, mb */
  sx?: SxProps<Theme>
  /** CardContent padding overrides */
  contentSx?: SxProps<Theme>
}

export default function SettingsCard({ children, sx, contentSx }: SettingsCardProps) {
  return (
    <Card variant="outlined" sx={{ borderRadius: 3, ...(sx as object) }}>
      <CardContent
        sx={{
          p: { xs: 2, md: 3 },
          '&:last-child': { pb: { xs: 2, md: 3 } },
          ...(contentSx as object),
        }}
      >
        {children}
      </CardContent>
    </Card>
  )
}
