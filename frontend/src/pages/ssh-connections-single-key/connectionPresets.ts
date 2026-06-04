import type { LucideIcon } from 'lucide-react'
import { Database, HardDrive, Server, Settings2, Warehouse } from 'lucide-react'
import type { DeployConnectionPayload } from './types'

export type RemoteMachineSetupPresetId = 'custom' | 'linux' | 'borgbase' | 'hetzner' | 'nas'

export interface RemoteMachineSetupPreset {
  id: RemoteMachineSetupPresetId
  icon: LucideIcon
  defaults: Partial<DeployConnectionPayload>
}

export const remoteMachineSetupPresets: RemoteMachineSetupPreset[] = [
  {
    id: 'custom',
    icon: Settings2,
    defaults: {},
  },
  {
    id: 'linux',
    icon: Server,
    defaults: {
      username: 'root',
      port: 22,
      use_sftp_mode: true,
      default_path: '',
      ssh_path_prefix: '',
      mount_point: '',
    },
  },
  {
    id: 'borgbase',
    icon: Database,
    defaults: {
      username: '',
      port: 22,
      use_sftp_mode: false,
      default_path: '/./repo',
      ssh_path_prefix: '',
      mount_point: 'borgbase',
    },
  },
  {
    id: 'hetzner',
    icon: Warehouse,
    defaults: {
      username: '',
      port: 23,
      use_sftp_mode: true,
      default_path: '/./borg-repository',
      ssh_path_prefix: '',
      mount_point: 'hetzner',
    },
  },
  {
    id: 'nas',
    icon: HardDrive,
    defaults: {
      username: '',
      port: 22,
      use_sftp_mode: false,
      default_path: '',
      ssh_path_prefix: '/volume1',
      mount_point: 'nas',
    },
  },
]
