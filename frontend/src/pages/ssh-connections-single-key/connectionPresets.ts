import type { ComponentType } from 'react'
import { Settings2 } from 'lucide-react'
import { SiBorgbackup, SiHetzner, SiLinux, SiSynology } from 'react-icons/si'
import type { DeployConnectionPayload } from './types'

export type RemoteMachineSetupPresetId = 'custom' | 'linux' | 'borgbase' | 'hetzner' | 'nas'

export interface RemoteMachineSetupPreset {
  id: RemoteMachineSetupPresetId
  icon: ComponentType<{ size?: number | string }>
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
    icon: SiLinux,
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
    icon: SiBorgbackup,
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
    icon: SiHetzner,
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
    icon: SiSynology,
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
