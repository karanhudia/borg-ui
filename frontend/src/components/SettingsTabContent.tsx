import { Box } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import type { ReactNode } from 'react'

interface SettingsTabContentProps {
  children: ReactNode
  /** Optional max width constraint — unconstrained by default */
  maxWidth?: number
  sx?: SxProps<Theme>
}

export default function SettingsTabContent({ children, maxWidth, sx }: SettingsTabContentProps) {
  return (
    <Box sx={{ ...(maxWidth ? { maxWidth, mx: 'auto' } : {}), ...(sx as object) }}>{children}</Box>
  )
}
