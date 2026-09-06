import { Box, alpha, useTheme } from '@mui/material'
import { FILE_KIND_ICONS, fileKindColor, fileKindFor } from './fileTypeStyle'

interface FileTypeIconProps {
  name: string
  type: 'file' | 'directory'
  size?: number
}

// A tinted square with the file's kind icon, the same token the archive
// browser rows and the details pane use.
export default function FileTypeIcon({ name, type, size = 32 }: FileTypeIconProps) {
  const theme = useTheme()
  const kind = fileKindFor(name, type)
  const color = fileKindColor(theme, kind)
  const Icon = FILE_KIND_ICONS[kind]
  return (
    <Box
      data-file-kind={kind}
      sx={{
        width: size,
        height: size,
        borderRadius: `${Math.round(size * 0.28)}px`,
        bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.18 : 0.12),
        color,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      <Icon size={Math.round(size * 0.55)} />
    </Box>
  )
}
