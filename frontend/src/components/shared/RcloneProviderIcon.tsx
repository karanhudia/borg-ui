import { Box, alpha, type SxProps, type Theme } from '@mui/material'
import { getRcloneProviderIconDefinition } from './rcloneProviderIconUtils'

interface RcloneProviderGlyphProps {
  provider: string | null | undefined
  size?: number
}

export function RcloneProviderGlyph({ provider, size = 18 }: RcloneProviderGlyphProps) {
  const definition = getRcloneProviderIconDefinition(provider)
  if (!definition) return null
  const { icon: Icon } = definition
  return <Icon aria-hidden size={size} />
}

interface RcloneProviderIconProps extends RcloneProviderGlyphProps {
  iconSize?: number
  sx?: SxProps<Theme>
}

export default function RcloneProviderIcon({
  provider,
  size = 36,
  iconSize = 18,
  sx,
}: RcloneProviderIconProps) {
  const definition = getRcloneProviderIconDefinition(provider)
  if (!definition) return null
  const { color } = definition

  return (
    <Box
      aria-hidden
      sx={[
        (theme) => ({
          width: size,
          height: size,
          borderRadius: 1.5,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          color,
          bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.2 : 0.1),
          border: '1px solid',
          borderColor: alpha(color, theme.palette.mode === 'dark' ? 0.36 : 0.22),
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <RcloneProviderGlyph provider={provider} size={iconSize} />
    </Box>
  )
}
