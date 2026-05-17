import axios from 'axios'
import { toast } from 'react-hot-toast'
import { BASE_PATH } from '@/utils/basePath'
import { API_BASE_URL, buildDownloadUrl } from '@/utils/downloadUrl'
import { attachAccessTokenHeader } from './authHeaders'
import type { RestoreLayout, RestorePathMetadata } from '@/utils/restorePaths'
import type { BackupPlan, BackupPlanData, SourceLocation } from '../types'

export type AuthTransportMode = 'jwt' | 'proxy' | 'insecure-no-auth'

let authTransportMode: AuthTransportMode = 'jwt'

export const setAuthTransportMode = (mode: AuthTransportMode) => {
  authTransportMode = mode
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use(attachAccessTokenHeader)

// Response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only redirect to login for 401 errors on authenticated endpoints
    // Don't redirect if:
    // 1. We're trying to login
    // 2. We're checking auth config
    // 3. We're in proxy auth mode (backend handles auth via proxy headers)
    if (error.response?.status === 403) {
      toast.error("You don't have permission to perform this action")
    }
    if (
      error.response?.status === 401 &&
      error.config?.url !== '/auth/login' &&
      error.config?.url !== '/auth/login/totp' &&
      error.config?.url !== '/auth/passkeys/authenticate/verify' &&
      error.config?.url !== '/auth/config' &&
      authTransportMode === 'jwt'
    ) {
      localStorage.removeItem('access_token')
      window.location.href = `${BASE_PATH}/login`
    }
    return Promise.reject(error)
  }
)

export interface RepositoryData {
  name?: string
  borg_version?: 1 | 2
  path?: string
  encryption?: string
  compression?: string
  source_directories?: string[]
  source_locations?: SourceLocation[]
  exclude_patterns?: string[]
  repository_type?: string
  execution_target?: 'local' | 'ssh' | 'agent'
  agent_machine_id?: number | null
  host?: string
  port?: number
  username?: string
  ssh_key_id?: number | null
  connection_id?: number | null
  remote_path?: string
  pre_backup_script?: string
  post_backup_script?: string
  pre_backup_script_parameters?: Record<string, string> | null
  post_backup_script_parameters?: Record<string, string> | null
  hook_timeout?: number
  pre_hook_timeout?: number
  post_hook_timeout?: number
  continue_on_hook_failure?: boolean
  skip_on_hook_failure?: boolean
  passphrase?: string
  mode?: 'full' | 'observe'
  custom_flags?: string | null
  bypass_lock?: boolean
  has_schedule?: boolean
  schedule_enabled?: boolean
  schedule_name?: string | null
  schedule_timezone?: string | null
  next_run?: string | null
  // Allow other properties for flexibility
  [key: string]: unknown
}

export interface SystemSettings {
  mount_timeout?: number
  info_timeout?: number
  list_timeout?: number
  init_timeout?: number
  backup_timeout?: number
  max_concurrent_scheduled_backups?: number
  max_concurrent_scheduled_checks?: number
  stats_refresh_interval_minutes?: number
  dashboard_backup_warning_days?: number
  dashboard_backup_critical_days?: number
  dashboard_check_warning_days?: number
  dashboard_check_critical_days?: number
  dashboard_compact_warning_days?: number
  dashboard_compact_critical_days?: number
  dashboard_restore_check_warning_days?: number
  dashboard_restore_check_critical_days?: number
  dashboard_observe_freshness_warning_days?: number
  dashboard_observe_freshness_critical_days?: number
  bypass_lock_on_info?: boolean
  bypass_lock_on_list?: boolean
  metrics_enabled?: boolean
  metrics_require_auth?: boolean
  metrics_token?: string
  metrics_token_set?: boolean
  borg2_fast_browse_beta_enabled?: boolean
  mqtt_beta_enabled?: boolean
  managed_agents_beta_enabled?: boolean
  [key: string]: unknown
}

export interface AuthorizationRoleDefinition {
  id: string
  rank: number
  scope: 'global' | 'repository'
}

export interface AuthorizationModel {
  global_roles: AuthorizationRoleDefinition[]
  repository_roles: AuthorizationRoleDefinition[]
  global_permission_rules: Record<string, string>
  repository_action_rules: Record<string, string>
  assignable_repository_roles_by_global_role: Record<string, string[]>
}

export interface AuthUserResponse {
  id: number
  username: string
  full_name?: string | null
  deployment_type?: 'individual' | 'enterprise' | null
  enterprise_name?: string | null
  email?: string | null
  is_active: boolean
  role: string
  all_repositories_role?: string | null
  auth_source?: string | null
  oidc_subject?: string | null
  oidc_link_supported?: boolean
  oidc_unlink_supported?: boolean
  must_change_password?: boolean
  totp_enabled?: boolean
  passkey_count?: number
  last_login?: string | null
  created_at: string
  global_permissions: string[]
}

export interface AuthLoginResponse {
  access_token?: string | null
  token_type?: string | null
  expires_in?: number | null
  must_change_password?: boolean
  totp_required?: boolean
  login_challenge_token?: string | null
}

export interface PasswordSetupCompleteResponse {
  must_change_password: boolean
}

export interface LogoutResponse {
  message: string
  logout_url?: string | null
}

export interface TotpStatusResponse {
  enabled: boolean
  recovery_codes_remaining: number
}

export interface TotpSetupResponse {
  setup_token: string
  secret: string
  otpauth_uri: string
  recovery_codes: string[]
}

export interface TotpEnableResponse {
  enabled: boolean
  recovery_codes: string[]
}

export interface PasskeyCredentialResponse {
  id: number
  name: string
  created_at: string
  last_used_at?: string | null
}

export interface PasskeyCeremonyResponse {
  ceremony_token: string
  options: Record<string, unknown>
}

export interface ProxyAuthWarning {
  code: string
  message: string
}

export interface AuthConfigResponse {
  proxy_auth_enabled: boolean
  insecure_no_auth_enabled: boolean
  authentication_required: boolean
  oidc_enabled?: boolean
  oidc_provider_name?: string | null
  oidc_disable_local_auth?: boolean
  oidc_link_supported?: boolean
  oidc_unlink_supported?: boolean
  oidc_account_linking_supported?: boolean
  proxy_auth_header?: string | null
  proxy_auth_role_header?: string | null
  proxy_auth_all_repositories_role_header?: string | null
  proxy_auth_email_header?: string | null
  proxy_auth_full_name_header?: string | null
  proxy_auth_health?: {
    enabled: boolean
    warnings: ProxyAuthWarning[]
  }
}

export interface OidcLinkStartResponse {
  authorization_url: string
}

// Generic type for object data
type ApiData = Record<string, unknown>

export interface SourceDiscoveryTypeOption {
  id: string
  label: string
  description: string
  status: string
  disabled: boolean
}

export interface SourceDiscoveryScriptDraft {
  name: string
  description: string
  content: string
  timeout: number
}

export interface SourceDiscoveryDatabase {
  id: string
  engine: string
  display_name: string
  backup_strategy: string
  source_directories: string[]
  client_commands: string[]
  documentation_url: string
  detected: boolean
  detection_source: string | null
  notes: string[]
  script_drafts: {
    pre_backup: SourceDiscoveryScriptDraft
    post_backup: SourceDiscoveryScriptDraft
  }
}

export interface SourceDiscoveryResponse {
  source_types: SourceDiscoveryTypeOption[]
  detections: SourceDiscoveryDatabase[]
  templates: SourceDiscoveryDatabase[]
}

export const authAPI = {
  getAuthConfig: () => api.get<AuthConfigResponse>('/auth/config'),
  getOidcLoginUrl: (returnTo?: string) => {
    const params = new URLSearchParams()
    if (returnTo) {
      params.set('return_to', returnTo)
    }
    const suffix = params.toString()
    return `${API_BASE_URL}/auth/oidc/login${suffix ? `?${suffix}` : ''}`
  },
  getOidcLinkUrl: (returnTo?: string) => {
    const params = new URLSearchParams()
    if (returnTo) {
      params.set('return_to', returnTo)
    }
    const suffix = params.toString()
    return `${API_BASE_URL}/auth/oidc/link${suffix ? `?${suffix}` : ''}`
  },
  beginOidcLink: (returnTo?: string) =>
    api.post<OidcLinkStartResponse>('/auth/oidc/link', { return_to: returnTo }),
  exchangeOidcToken: () => api.post<AuthLoginResponse>('/auth/oidc/exchange'),
  unlinkOidc: () => api.post('/auth/oidc/unlink'),

  login: (username: string, password: string) =>
    api.post<AuthLoginResponse>(
      '/auth/login',
      `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
      {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }
    ),

  verifyTotpLogin: (loginChallengeToken: string, code: string) =>
    api.post<AuthLoginResponse>('/auth/login/totp', {
      login_challenge_token: loginChallengeToken,
      code,
    }),

  logout: () => api.post<LogoutResponse>('/auth/logout'),

  refresh: () => api.post('/auth/refresh'),

  getProfile: () => api.get('/auth/me'),
  getAuthorizationModel: () => api.get<AuthorizationModel>('/auth/authorization-model'),
  getTotpStatus: () => api.get<TotpStatusResponse>('/auth/totp'),
  beginTotpSetup: (currentPassword: string) =>
    api.post<TotpSetupResponse>('/auth/totp/setup', { current_password: currentPassword }),
  enableTotp: (setupToken: string, code: string) =>
    api.post<TotpEnableResponse>('/auth/totp/enable', { setup_token: setupToken, code }),
  disableTotp: (currentPassword: string, code: string) =>
    api.post('/auth/totp/disable', { current_password: currentPassword, code }),
  listPasskeys: () => api.get<PasskeyCredentialResponse[]>('/auth/passkeys'),
  beginPasskeyRegistration: (currentPassword: string) =>
    api.post<PasskeyCeremonyResponse>('/auth/passkeys/register/options', {
      current_password: currentPassword,
    }),
  finishPasskeyRegistration: (ceremonyToken: string, credential: unknown, name?: string) =>
    api.post<PasskeyCredentialResponse>('/auth/passkeys/register/verify', {
      ceremony_token: ceremonyToken,
      credential,
      name,
    }),
  deletePasskey: (passkeyId: number) => api.delete(`/auth/passkeys/${passkeyId}`),
  beginPasskeyAuthentication: () =>
    api.post<PasskeyCeremonyResponse>('/auth/passkeys/authenticate/options'),
  finishPasskeyAuthentication: (ceremonyToken: string, credential: unknown) =>
    api.post<AuthLoginResponse>('/auth/passkeys/authenticate/verify', {
      ceremony_token: ceremonyToken,
      credential,
    }),

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  skipPasswordSetup: () => api.post<PasswordSetupCompleteResponse>('/auth/password-setup/skip'),
}

export const dashboardAPI = {
  getStatus: () => api.get('/dashboard/status'),
  getMetrics: () => api.get('/dashboard/metrics'),
  getSchedule: () => api.get('/dashboard/schedule'),
  getOverview: () => api.get('/dashboard/overview'),
}

export const licensingAPI = {
  refresh: () => api.post('/system/licensing/refresh'),
  activate: (licenseKey: string) =>
    api.post('/system/licensing/activate', { license_key: licenseKey }),
  deactivate: () => api.post('/system/licensing/deactivate'),
}

export const backupAPI = {
  startBackup: (repository?: string) => api.post('/backup/start', { repository }),
  getStatus: (jobId: string) => api.get(`/backup/status/${jobId}`),
  getAllJobs: () => api.get('/backup/jobs'),
  getManualJobs: (repository?: string) =>
    api.get('/backup/jobs', {
      params: {
        manual_only: true,
        ...(repository ? { repository } : {}),
      },
    }),
  getScheduledJobs: () => api.get('/backup/jobs?scheduled_only=true'),
  cancelJob: (jobId: string) => api.post(`/backup/cancel/${jobId}`),
  // Download logs as file (only for failed/cancelled backups)
  downloadLogs: (jobId: string) =>
    window.open(buildDownloadUrl(`/backup/logs/${jobId}/download`), '_blank'),
}

export const archivesAPI = {
  listArchives: (repository: string) => api.get(`/archives/${repository}`),
  getArchiveInfo: (repository: string, archive: string) =>
    api.get(`/archives/${repository}/${archive}`),
  listContents: (repository: string, archive: string, path?: string) =>
    api.get(`/archives/${repository}/${archive}/contents`, { params: { path } }),
  deleteArchive: (repository: string, archive: string) =>
    api.delete(
      `/archives/${encodeURIComponent(archive)}?repository=${encodeURIComponent(repository)}`
    ),
  downloadFile: (repository: string, archive: string, filePath: string) =>
    window.location.assign(
      buildDownloadUrl('/archives/download', {
        repository,
        archive,
        file_path: filePath,
      })
    ),
}

export const restoreAPI = {
  previewRestore: (repository: string, archive: string, paths: string[]) =>
    api.post('/restore/preview', { repository, archive, paths }),
  startRestore: (
    repository: string,
    archive: string,
    paths: string[],
    destination: string,
    repository_id: number,
    destination_type: string = 'local',
    destination_connection_id: number | null = null,
    restore_layout: RestoreLayout = 'preserve_path',
    path_metadata: RestorePathMetadata[] = []
  ) =>
    api.post('/restore/start', {
      repository,
      archive,
      paths,
      destination,
      repository_id,
      destination_type,
      destination_connection_id,
      restore_layout,
      path_metadata,
    }),
  getRestoreJobs: () => api.get('/restore/jobs'),
  getRestoreStatus: (jobId: number) => api.get(`/restore/status/${jobId}`),
}
export const settingsAPI = {
  // System settings
  getSystemSettings: () => api.get('/settings/system'),
  updateSystemSettings: (settings: SystemSettings) => api.put('/settings/system', settings),
  refreshAllStats: () => api.post('/settings/refresh-stats'),

  // User management
  getUsers: () => api.get('/settings/users'),
  createUser: (userData: ApiData) => api.post('/settings/users', userData),
  updateUser: (userId: number, userData: ApiData) => api.put(`/settings/users/${userId}`, userData),
  deleteUser: (userId: number) => api.delete(`/settings/users/${userId}`),
  resetUserPassword: (userId: number, newPassword: string) =>
    api.post(`/settings/users/${userId}/reset-password`, { new_password: newPassword }),

  // Profile management
  getProfile: () => api.get('/settings/profile'),
  updateProfile: (profileData: ApiData) => api.put('/settings/profile', profileData),
  changePassword: (passwordData: ApiData) => api.post('/settings/change-password', passwordData),

  // User preferences
  getPreferences: () => api.get('/settings/preferences'),
  updatePreferences: (preferences: ApiData) => api.put('/settings/preferences', preferences),

  // System maintenance
  cleanupSystem: () => api.post('/settings/system/cleanup'),

  // Log management
  getLogStorageStats: () => api.get('/settings/system/logs/storage'),
  manualLogCleanup: () => api.post('/settings/system/logs/cleanup'),

  // Cache management
  getCacheStats: () => api.get('/settings/cache/stats'),
  clearCache: (repositoryId?: number) =>
    api.post('/settings/cache/clear', null, { params: { repository_id: repositoryId } }),
  updateCacheSettings: (
    ttlMinutes: number,
    maxSizeMb: number,
    redisUrl?: string,
    browseMaxItems?: number,
    browseMaxMemoryMb?: number
  ) => {
    const params: Record<string, string | number> = {
      cache_ttl_minutes: ttlMinutes,
      cache_max_size_mb: maxSizeMb,
    }
    // Only include redis_url if it's provided
    if (redisUrl !== undefined) {
      params.redis_url = redisUrl
    }
    // Only include browse limits if provided
    if (browseMaxItems !== undefined) {
      params.browse_max_items = browseMaxItems
    }
    if (browseMaxMemoryMb !== undefined) {
      params.browse_max_memory_mb = browseMaxMemoryMb
    }
    return api.put('/settings/cache/settings', null, { params })
  },
}

export const tokensAPI = {
  list: () =>
    api.get<
      {
        id: number
        name: string
        prefix: string
        created_at: string
        last_used_at: string | null
      }[]
    >('/settings/tokens'),
  generate: (name: string) =>
    api.post<{ id: number; name: string; token: string; prefix: string; created_at: string }>(
      '/settings/tokens',
      { name }
    ),
  revoke: (id: number) => api.delete(`/settings/tokens/${id}`),
}

interface PermissionResponse {
  id: number
  user_id: number
  repository_id: number
  repository_name: string
  role: string
  created_at: string
}

export interface PermissionScopeResponse {
  all_repositories_role: string | null
}

export interface AuthEventRecord {
  id: number
  event_type: string
  auth_source: string
  username: string | null
  email: string | null
  success: boolean
  detail: string | null
  actor_user_id: number | null
  created_at: string
}

export const permissionsAPI = {
  getMyPermissions: () => api.get<PermissionResponse[]>('/settings/permissions/me'),
  getMyPermissionScope: () => api.get<PermissionScopeResponse>('/settings/permissions/me/scope'),
  getUserPermissions: (userId: number) =>
    api.get<PermissionResponse[]>(`/settings/users/${userId}/permissions`),
  getUserPermissionScope: (userId: number) =>
    api.get<PermissionScopeResponse>(`/settings/users/${userId}/permissions/scope`),
  assign: (userId: number, data: { repository_id: number; role: string }) =>
    api.post<PermissionResponse>(`/settings/users/${userId}/permissions`, data),
  update: (userId: number, repoId: number, role: string) =>
    api.put<PermissionResponse>(`/settings/users/${userId}/permissions/${repoId}`, { role }),
  updateScope: (userId: number, all_repositories_role: string | null) =>
    api.put<PermissionScopeResponse>(`/settings/users/${userId}/permissions/scope`, {
      all_repositories_role,
    }),
  remove: (userId: number, repoId: number) =>
    api.delete(`/settings/users/${userId}/permissions/${repoId}`),
}

export const authAPIAdmin = {
  listEvents: (limit: number = 50) =>
    api.get<AuthEventRecord[]>('/auth/events', {
      params: { limit },
    }),
}

// Repositories API
export const repositoriesAPI = {
  getRepositories: () => api.get('/repositories/'),
  createRepository: (data: RepositoryData) => api.post('/repositories/', data),
  importRepository: (data: RepositoryData) => api.post('/repositories/import', data),
  uploadKeyfile: (id: number, keyfile: File) => {
    const formData = new FormData()
    formData.append('keyfile', keyfile)
    return api.post(`/repositories/${id}/keyfile`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  },
  downloadKeyfile: (id: number) => api.get(`/repositories/${id}/keyfile`, { responseType: 'blob' }),
  getRepository: (id: number) => api.get(`/repositories/${id}`),
  updateRepository: (id: number, data: RepositoryData) => api.put(`/repositories/${id}`, data),
  deleteRepository: (id: number) => api.delete(`/repositories/${id}`),
  checkRepository: (id: number, maxDuration: number = 3600) =>
    api.post(`/repositories/${id}/check`, { max_duration: maxDuration }),
  restoreCheckRepository: (
    id: number,
    data?: {
      paths?: string[]
      full_archive?: boolean
    }
  ) => api.post(`/repositories/${id}/restore-check`, data || {}),
  compactRepository: (id: number) => api.post(`/repositories/${id}/compact`),
  pruneRepository: (id: number, data: ApiData) => api.post(`/repositories/${id}/prune`, data),
  breakLock: (id: number) => api.post(`/repositories/${id}/break-lock`),
  getRepositoryStats: (id: number) => api.get(`/repositories/${id}/stats`),
  listRepositoryArchives: (id: number) => api.get(`/repositories/${id}/archives`),
  getRepositoryInfo: (id: number) => api.get(`/repositories/${id}/info`),
  // Check/Compact job management
  getCheckJobStatus: (jobId: number) => api.get(`/repositories/check-jobs/${jobId}`),
  getRepositoryCheckJobs: (id: number, limit?: number, scheduledOnly: boolean = false) =>
    api.get(`/repositories/${id}/check-jobs`, {
      params: { limit, scheduled_only: scheduledOnly },
    }),
  getRestoreCheckJobStatus: (jobId: number) => api.get(`/repositories/restore-check-jobs/${jobId}`),
  getRepositoryRestoreCheckJobs: (id: number, limit?: number) =>
    api.get(`/repositories/${id}/restore-check-jobs`, { params: { limit } }),
  getCompactJobStatus: (jobId: number) => api.get(`/repositories/compact-jobs/${jobId}`),
  getRepositoryCompactJobs: (id: number, limit?: number) =>
    api.get(`/repositories/${id}/compact-jobs`, { params: { limit } }),
  getRepositoryPruneJobs: (id: number, limit?: number) =>
    api.get(`/repositories/${id}/prune-jobs`, { params: { limit } }),
  getRunningJobs: (id: number) => api.get(`/repositories/${id}/running-jobs`),
  // Check schedule management
  getCheckSchedule: (id: number) => api.get(`/repositories/${id}/check-schedule`),
  updateCheckSchedule: (id: number, data: ApiData) =>
    api.put(`/repositories/${id}/check-schedule`, data),
  getRestoreCheckSchedule: (id: number) => api.get(`/repositories/${id}/restore-check-schedule`),
  updateRestoreCheckSchedule: (id: number, data: ApiData) =>
    api.put(`/repositories/${id}/restore-check-schedule`, data),
  list: () => api.get('/repositories/'),
  startCheck: (id: number, data: ApiData) => api.post(`/repositories/${id}/check`, data),
}

export const backupPlansAPI = {
  list: () => api.get('/backup-plans/'),
  create: (data: BackupPlanData) => api.post('/backup-plans/', data),
  createFromRepository: (
    id: number,
    data: {
      name?: string
      copy_schedule?: boolean
      disable_repository_schedule?: boolean
      move_source_settings?: boolean
    } = {}
  ) =>
    api.post<{
      backup_plan: BackupPlan
      source_repository_id: number
      copied_schedule_id?: number | null
      repository_schedule_disabled: boolean
      repository_schedule_disable_reason?: string | null
      source_settings_moved: boolean
    }>(`/backup-plans/from-repository/${id}`, data),
  get: (id: number) => api.get(`/backup-plans/${id}`),
  update: (id: number, data: BackupPlanData) => api.put(`/backup-plans/${id}`, data),
  delete: (id: number) => api.delete(`/backup-plans/${id}`),
  toggle: (id: number) => api.post(`/backup-plans/${id}/toggle`),
  run: (id: number) => api.post(`/backup-plans/${id}/run`),
  listRuns: () => api.get('/backup-plans/runs'),
  getRun: (id: number) => api.get(`/backup-plans/runs/${id}`),
  cancelRun: (id: number) => api.post(`/backup-plans/runs/${id}/cancel`),
  listRunsForPlan: (id: number) => api.get(`/backup-plans/${id}/runs`),
}

// SSH Keys API
export const sshKeysAPI = {
  // Single-key system
  getSystemKey: () => api.get('/ssh-keys/system-key'),
  generateSSHKey: (data: ApiData) => api.post('/ssh-keys/generate', data),

  // Legacy multi-key endpoints (deprecated)
  getSSHKeys: () => api.get('/ssh-keys'),
  createSSHKey: (data: ApiData) => api.post('/ssh-keys', data),
  quickSetup: (data: ApiData) => api.post('/ssh-keys/quick-setup', data),
  getSSHKey: (id: number) => api.get(`/ssh-keys/${id}`),
  updateSSHKey: (id: number, data: ApiData) => api.put(`/ssh-keys/${id}`, data),
  deleteSSHKey: (id: number) => api.delete(`/ssh-keys/${id}`),

  // Connection management
  deploySSHKey: (id: number, data: ApiData) => api.post(`/ssh-keys/${id}/deploy`, data),
  testSSHConnection: (id: number, data: ApiData) =>
    api.post(`/ssh-keys/${id}/test-connection`, data),
  testExistingConnection: (connectionId: number) =>
    api.post(`/ssh-keys/connections/${connectionId}/test`),
  getSSHConnections: () => api.get('/ssh-keys/connections'),
  updateSSHConnection: (connectionId: number, data: ApiData) =>
    api.put(`/ssh-keys/connections/${connectionId}`, data),
  deleteSSHConnection: (connectionId: number) =>
    api.delete(`/ssh-keys/connections/${connectionId}`),
  refreshConnectionStorage: (connectionId: number) =>
    api.post(`/ssh-keys/connections/${connectionId}/refresh-storage`),
  redeployKeyToConnection: (connectionId: number, password: string) =>
    api.post(`/ssh-keys/connections/${connectionId}/redeploy`, { password }),
  importSSHKey: (data: ApiData) => api.post('/ssh-keys/import', data),
}

export interface AgentMachineResponse {
  id: number
  name: string
  agent_id: string
  hostname?: string | null
  os?: string | null
  arch?: string | null
  agent_version?: string | null
  borg_versions?: Array<Record<string, unknown>> | null
  capabilities?: string[] | null
  labels?: Record<string, unknown> | null
  status: string
  last_seen_at?: string | null
  last_error?: string | null
  created_at: string
  updated_at: string
}

export interface AgentEnrollmentTokenSummary {
  id: number
  name: string
  token_prefix: string
  expires_at: string
  used_at?: string | null
  used_by_agent_id?: number | null
  revoked_at?: string | null
  created_at: string
}

export interface AgentEnrollmentTokenCreated extends AgentEnrollmentTokenSummary {
  token: string
}

export interface AgentJobResponse {
  id: number
  agent_machine_id: number
  backup_job_id?: number | null
  job_type: string
  status: string
  payload: Record<string, unknown>
  result?: Record<string, unknown> | null
  claimed_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  progress_percent?: number | null
  current_file?: string | null
  created_at: string
  updated_at: string
}

export interface AgentJobLogEntryResponse {
  id: number
  agent_job_id: number
  sequence: number
  stream: string
  message: string
  created_at: string
  received_at: string
}

export interface AgentBackupJobCreate {
  repository_path: string
  archive_name: string
  source_paths: string[]
  borg_version?: 1 | 2
  borg_binary?: string | null
  compression?: string
  exclude_patterns?: string[]
  custom_flags?: string[]
  remote_path?: string | null
  repository_id?: number | null
  secrets?: Record<string, unknown>
}

export const managedAgentsAPI = {
  listAgents: () => api.get<AgentMachineResponse[]>('/managed-machines/agents'),
  revokeAgent: (agentId: number) => api.post(`/managed-machines/agents/${agentId}/revoke`),
  createEnrollmentToken: (data: { name: string; expires_in_minutes: number }) =>
    api.post<AgentEnrollmentTokenCreated>('/managed-machines/enrollment-tokens', data),
  listEnrollmentTokens: () =>
    api.get<AgentEnrollmentTokenSummary[]>('/managed-machines/enrollment-tokens'),
  revokeEnrollmentToken: (tokenId: number) =>
    api.post(`/managed-machines/enrollment-tokens/${tokenId}/revoke`),
  listJobs: () => api.get<AgentJobResponse[]>('/managed-machines/agent-jobs'),
  createBackupJob: (agentId: number, data: AgentBackupJobCreate) =>
    api.post<AgentJobResponse>(`/managed-machines/agents/${agentId}/backup-jobs`, data),
  cancelJob: (jobId: number) =>
    api.post<AgentJobResponse>(`/managed-machines/agent-jobs/${jobId}/cancel`),
  listJobLogs: (jobId: number) =>
    api.get<AgentJobLogEntryResponse[]>(`/managed-machines/agent-jobs/${jobId}/logs`),
}

// Schedule API
export const scheduleAPI = {
  getScheduledJobs: () => api.get('/schedule/'),
  createScheduledJob: (data: ApiData) => api.post('/schedule/', data),
  getScheduledJob: (id: number) => api.get(`/schedule/${id}`),
  updateScheduledJob: (id: number, data: ApiData) => api.put(`/schedule/${id}`, data),
  deleteScheduledJob: (id: number) => api.delete(`/schedule/${id}`),
  toggleScheduledJob: (id: number) => api.post(`/schedule/${id}/toggle`),
  runScheduledJobNow: (id: number) => api.post(`/schedule/${id}/run-now`),
  duplicateScheduledJob: (id: number) => api.post(`/schedule/${id}/duplicate`),
  validateCronExpression: (data: ApiData) => api.post('/schedule/validate-cron', data),
  getCronPresets: () => api.get('/schedule/cron-presets'),
  getUpcomingJobs: (hours?: number) => api.get('/schedule/upcoming-jobs', { params: { hours } }),
}

export const notificationsAPI = {
  list: () => api.get('/notifications'),
  get: (id: number) => api.get(`/notifications/${id}`),
  create: (data: ApiData) => api.post('/notifications', data),
  update: (id: number, data: ApiData) => api.put(`/notifications/${id}`, data),
  delete: (id: number) => api.delete(`/notifications/${id}`),
  test: (serviceUrl: string) => api.post('/notifications/test', { service_url: serviceUrl }),
}

export const activityAPI = {
  list: (params?: ApiData) => api.get('/activity/recent', { params }),
  getLogs: (jobType: string, jobId: string | number, offset: number = 0) =>
    api.get(`/activity/${jobType}/${jobId}/logs`, { params: { offset } }),
  cancelJob: (jobType: string, jobId: string | number) =>
    api.post(`/activity/${jobType}/${jobId}/cancel`),
  deleteJob: (jobType: string, jobId: string | number) =>
    api.delete(`/activity/${jobType}/${jobId}`),
  downloadLogs: (jobType: string, jobId: number) =>
    window.open(buildDownloadUrl(`/activity/${jobType}/${jobId}/logs/download`), '_blank'),
}

export const configExportImportAPI = {
  // Export configuration to borgmatic YAML
  exportBorgmatic: (repositoryIds?: number[], includeSchedules = true) =>
    api.post(
      '/config/export/borgmatic',
      {
        repository_ids: repositoryIds,
        include_schedules: includeSchedules,
      },
      {
        responseType: 'blob', // Important for file download
      }
    ),

  // Import borgmatic YAML configuration
  importBorgmatic: (file: File, mergeStrategy = 'skip_duplicates', dryRun = false) => {
    const formData = new FormData()
    formData.append('file', file)

    return api.post(
      `/config/import/borgmatic?merge_strategy=${mergeStrategy}&dry_run=${dryRun}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
  },

  // Get list of repositories available for export
  listExportableRepositories: () => api.get('/config/export/repositories'),
}

export const scriptsAPI = {
  // List all scripts from library
  list: (params?: { category?: string; search?: string }) => api.get('/scripts', { params }),

  // Get a specific script
  get: (scriptId: number) => api.get(`/scripts/${scriptId}`),

  // Create a new script
  create: (data: ApiData) => api.post('/scripts', data),

  // Update a script
  update: (scriptId: number, data: ApiData) => api.put(`/scripts/${scriptId}`, data),

  // Delete a script
  delete: (scriptId: number) => api.delete(`/scripts/${scriptId}`),
}

export const sourceDiscoveryAPI = {
  databases: () => api.get<SourceDiscoveryResponse>('/source-discovery/databases'),
}

export const mountsAPI = {
  // Mount a Borg repository or archive
  mountBorgArchive: (data: {
    repository_id: number
    archive_name?: string
    mount_point?: string
  }) => api.post('/mounts/borg', data),

  // Unmount a mounted archive
  unmountBorgArchive: (mountId: string, force: boolean = false) =>
    api.post(`/mounts/borg/unmount/${mountId}`, {}, { params: { force } }),

  // List all active mounts
  listMounts: () => api.get('/mounts'),

  // Get specific mount info
  getMountInfo: (mountId: string) => api.get(`/mounts/${mountId}`),
}

export default api
