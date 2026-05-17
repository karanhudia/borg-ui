import type { BackupPlanPayloadState } from '../../utils/backupPlanPayload'

export type WizardState = BackupPlanPayloadState

export interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id: number
  default_path?: string
  mount_point?: string
  status: string
}

export interface ScriptParameter {
  name: string
  type: 'text' | 'password'
  default: string
  description: string
  required: boolean
}

export interface ScriptOption {
  id: number
  name: string
  description?: string | null
  parameters?: ScriptParameter[] | null
}

export interface BasicRepositoryState {
  name: string
  borgVersion: 1 | 2
  path: string
  encryption: string
  passphrase: string
}
