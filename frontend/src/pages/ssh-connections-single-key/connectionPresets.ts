import type { ComponentType } from 'react'
import { Settings2 } from 'lucide-react'
import { SiBorgbackup, SiHetzner, SiLinux, SiSynology } from 'react-icons/si'
import type { DeployConnectionPayload } from './types'

export type RemoteMachineSetupPresetId = 'custom' | 'linux' | 'borgbase' | 'hetzner' | 'nas'

export interface RemoteMachineSetupPreset {
  id: RemoteMachineSetupPresetId
  icon: ComponentType<{ size?: number | string }>
  brandColor: string
  hostPlaceholder: string
  usernamePlaceholder: string
  defaults: Partial<DeployConnectionPayload>
}

export const remoteMachineSetupPresets: RemoteMachineSetupPreset[] = [
  {
    id: 'custom',
    icon: Settings2,
    brandColor: '#64748B',
    hostPlaceholder: 'backup.example.com',
    usernamePlaceholder: 'backup',
    defaults: {},
  },
  {
    id: 'linux',
    icon: SiLinux,
    brandColor: '#FCC624',
    hostPlaceholder: 'backup.example.com',
    usernamePlaceholder: 'backup',
    defaults: {
      port: 22,
      use_sftp_mode: true,
      default_path: '/home/backup',
      ssh_path_prefix: '',
      mount_point: 'linux-server',
    },
  },
  {
    id: 'borgbase',
    icon: SiBorgbackup,
    brandColor: '#00DD00',
    hostPlaceholder: 'mmvz9gp4.repo.borgbase.com',
    usernamePlaceholder: 'mmvz9gp4',
    defaults: {
      port: 22,
      use_sftp_mode: false,
      default_path: '/./repo',
      ssh_path_prefix: '',
      mount_point: 'borgbase',
    },
  },
  {
    id: 'hetzner',
    icon: SiHetzner,
    brandColor: '#D50C2D',
    hostPlaceholder: 'u123456.your-storagebox.de',
    usernamePlaceholder: 'u123456',
    defaults: {
      port: 23,
      use_sftp_mode: true,
      default_path: '/home',
      ssh_path_prefix: '',
      mount_point: 'hetzner-storage-box',
    },
  },
  {
    id: 'nas',
    icon: SiSynology,
    brandColor: '#B5B5B6',
    hostPlaceholder: 'diskstation.local',
    usernamePlaceholder: 'backup',
    defaults: {
      port: 22,
      use_sftp_mode: false,
      default_path: '/backups',
      ssh_path_prefix: '/volume1',
      mount_point: 'nas',
    },
  },
]
