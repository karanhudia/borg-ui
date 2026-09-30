import { Box } from '@mui/material'
import { AppWindow } from 'lucide-react'

import type { AppTemplate } from '../../services/api'

/**
 * The app's official logo. Rendered through <img>, so any script inside the
 * SVG never runs.
 */
export default function AppLogo({ app, size = 24 }: { app: AppTemplate; size?: number }) {
  if (!app.logo_svg) return <AppWindow size={size} aria-hidden />
  return (
    <Box
      component="img"
      src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(app.logo_svg)}`}
      alt=""
      aria-hidden
      sx={{ width: size, height: size, display: 'block', objectFit: 'contain' }}
    />
  )
}
