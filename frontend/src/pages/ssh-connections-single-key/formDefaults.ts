import type {
  DeployConnectionPayload,
  ImportKeyPayload,
  TestConnectionPayload,
  UpdateConnectionPayload,
} from './types'

export const createImportForm = (): ImportKeyPayload => ({
  name: 'System SSH Key',
  private_key_path: '',
  public_key_path: '',
  description: 'Imported system SSH key for all remote connections',
})

export const createConnectionForm = (): DeployConnectionPayload => ({
  host: '',
  username: '',
  port: 22,
  password: '',
  use_sftp_mode: true,
  default_path: '',
  ssh_path_prefix: '',
  mount_point: '',
})

export const createTestConnectionForm = (): TestConnectionPayload => ({
  host: '',
  username: '',
  port: 22,
})

export const createEditConnectionForm = (): UpdateConnectionPayload => ({
  host: '',
  username: '',
  port: 22,
  use_sftp_mode: true,
  use_sudo: false,
  default_path: '',
  ssh_path_prefix: '',
  mount_point: '',
})
