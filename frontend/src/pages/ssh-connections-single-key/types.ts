export interface StorageInfo {
  total: number
  total_formatted: string
  used: number
  used_formatted: string
  available: number
  available_formatted: string
  percent_used: number
  last_check?: string | null
}

export interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  use_sftp_mode: boolean
  use_sudo: boolean
  default_path?: string
  ssh_path_prefix?: string
  mount_point?: string
  status: string
  last_test?: string
  last_success?: string
  error_message?: string
  storage?: StorageInfo | null
  created_at: string
}

export interface SystemSSHKey {
  id: number
  name?: string
  key_type?: string
  fingerprint?: string
  public_key?: string
}

export interface ImportKeyPayload extends Record<string, unknown> {
  name: string
  private_key_path: string
  public_key_path: string
  description: string
}

export interface DeployConnectionPayload extends Record<string, unknown> {
  host: string
  username: string
  port: number
  password: string
  use_sftp_mode: boolean
  default_path: string
  ssh_path_prefix: string
  mount_point: string
}

export interface TestConnectionPayload extends Record<string, unknown> {
  host: string
  username: string
  port: number
}

export interface UpdateConnectionPayload extends Record<string, unknown> {
  host: string
  username: string
  port: number
  use_sftp_mode: boolean
  use_sudo: boolean
  default_path: string
  ssh_path_prefix: string
  mount_point: string
}
