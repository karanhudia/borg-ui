import {
  Archive,
  Cloud,
  CloudDownload,
  CloudUpload,
  FolderSync,
  HardDrive,
  Network,
  Server,
  Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { IconType } from 'react-icons'
import {
  TbBrandAws,
  TbBrandAzure,
  TbBrandDropbox,
  TbBrandGoogleDrive,
  TbBrandYandex,
  TbBrandOnedrive,
} from 'react-icons/tb'
import {
  SiBackblaze,
  SiBox,
  SiCitrix,
  SiGooglecloudstorage,
  SiGooglephotos,
  SiHuawei,
  SiMaildotru,
  SiZoho,
} from 'react-icons/si'

export type ProviderIconDefinition = {
  icon: IconType | LucideIcon
  color: string
}

const PROVIDER_ICONS: Record<string, ProviderIconDefinition> = {
  drive: { icon: TbBrandGoogleDrive, color: '#1a73e8' },
  onedrive: { icon: TbBrandOnedrive, color: '#0078d4' },
  dropbox: { icon: TbBrandDropbox, color: '#0061ff' },
  box: { icon: SiBox, color: '#0061d5' },
  gcs: { icon: SiGooglecloudstorage, color: '#4285f4' },
  gphotos: { icon: SiGooglephotos, color: '#4285f4' },
  hidrive: { icon: CloudUpload, color: '#00a6d6' },
  huaweidrive: { icon: SiHuawei, color: '#cf0a2c' },
  jottacloud: { icon: Cloud, color: '#ec1c24' },
  mailru: { icon: SiMaildotru, color: '#168de2' },
  pcloud: { icon: CloudDownload, color: '#0085ff' },
  premiumizeme: { icon: Archive, color: '#ef7d00' },
  putio: { icon: FolderSync, color: '#00a3e0' },
  sharefile: { icon: SiCitrix, color: '#452170' },
  yandex: { icon: TbBrandYandex, color: '#fc3f1d' },
  zoho: { icon: SiZoho, color: '#e42527' },
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

export const getRcloneProviderIconDefinition = (
  provider: string | null | undefined,
  allowFallback = true
): ProviderIconDefinition | null => {
  const normalized = normalizeProvider(provider)
  if (PROVIDER_ICONS[normalized]) return PROVIDER_ICONS[normalized]
  if (normalized.includes('s3')) return PROVIDER_ICONS.s3
  if (normalized.includes('google') && normalized.includes('photo')) return PROVIDER_ICONS.gphotos
  if (normalized.includes('google') || normalized.includes('gcs')) return PROVIDER_ICONS.gcs
  if (normalized.includes('azure')) return PROVIDER_ICONS.azureblob
  if (normalized.includes('yandex')) return PROVIDER_ICONS.yandex
  if (normalized.includes('mailru') || normalized.includes('mail.ru')) return PROVIDER_ICONS.mailru
  if (normalized.includes('webdav')) return PROVIDER_ICONS.webdav
  if (normalized.includes('sftp') || normalized.includes('ssh')) return PROVIDER_ICONS.sftp
  if (normalized.includes('local')) return PROVIDER_ICONS.local
  return allowFallback ? { icon: Cloud, color: '#64748b' } : null
}
