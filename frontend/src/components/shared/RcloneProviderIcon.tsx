import { Box, alpha, type SxProps, type Theme } from '@mui/material'
import { Cloud, HardDrive, Network, Server, Settings } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { IconType } from 'react-icons'
import {
  TbBrandAws,
  TbBrandAzure,
  TbBrandDropbox,
  TbBrandGoogleDrive,
  TbBrandOnedrive,
} from 'react-icons/tb'
import { SiBackblaze, SiBox } from 'react-icons/si'

type ProviderIconDefinition = {
  icon: IconType | LucideIcon
  color: string
}

const PROVIDER_ICONS: Record<string, ProviderIconDefinition> = {
  drive: { icon: TbBrandGoogleDrive, color: '#1a73e8' },
  onedrive: { icon: TbBrandOnedrive, color: '#0078d4' },
  dropbox: { icon: TbBrandDropbox, color: '#0061ff' },
  box: { icon: SiBox, color: '#0061d5' },
  s3: { icon: TbBrandAws, color: '#ff9900' },
  b2: { icon: SiBackblaze, color: '#e01f2d' },
  azureblob: { icon: TbBrandAzure, color: '#0078d4' },
  webdav: { icon: Network, color: '#0891b2' },
  sftp: { icon: Server, color: '#64748b' },
  local: { icon: HardDrive, color: '#64748b' },
  custom: { icon: Settings, color: '#7c3aed' },
}

const normalizeProvider = (provider: string | null | undefined) =>
  (provider || 'custom').trim().toLowerCase()

const getRcloneProviderIconDefinition = (
  provider: string | null | undefined
): ProviderIconDefinition => {
  const normalized = normalizeProvider(provider)
  if (PROVIDER_ICONS[normalized]) return PROVIDER_ICONS[normalized]
  if (normalized.includes('s3')) return PROVIDER_ICONS.s3
  if (normalized.includes('webdav')) return PROVIDER_ICONS.webdav
  if (normalized.includes('sftp') || normalized.includes('ssh')) return PROVIDER_ICONS.sftp
  if (normalized.includes('local')) return PROVIDER_ICONS.local
  return { icon: Cloud, color: '#64748b' }
}

interface RcloneProviderGlyphProps {
  provider: string | null | undefined
  size?: number
}

export function RcloneProviderGlyph({ provider, size = 18 }: RcloneProviderGlyphProps) {
  const { icon: Icon } = getRcloneProviderIconDefinition(provider)
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
  const { color } = getRcloneProviderIconDefinition(provider)

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
