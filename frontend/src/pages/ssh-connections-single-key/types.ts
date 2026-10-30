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
  shell_restricted?: boolean
  last_test?: string
  last_success?: string
  error_message?: string
  storage?: StorageInfo | null
  host_key_verified?: boolean
  host_key_fingerprint?: string | null
  created_at: string
}

export interface SystemSSHKey {
  id: number
  name?: string
  key_type?: string
  fingerprint?: string
  public_key?: string
}

/** A row of GET /ssh-keys: the system key and any extra keys. */
export interface SSHKeySummary {
  id: number
  name: string
  key_type: string
  fingerprint?: string | null
  public_key?: string
  is_system_key: boolean
  connection_count: number
}

export interface ImportKeyPayload extends Record<string, unknown> {
  name: string
  private_key_path: string
  public_key_path: string
  description: string
}

export interface DeployConnectionPayload extends Record<string, unknown> {
  /** Key to deploy; the system key when unset. Sent in the URL, not the body. */
  ssh_key_id?: number
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
  ssh_key_id?: number
  host: string
  username: string
  port: number
  use_sftp_mode: boolean
  use_sudo: boolean
  default_path: string
  ssh_path_prefix: string
  mount_point: string
}
