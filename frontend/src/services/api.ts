import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const authAPI = {
  login: (username: string, password: string) =>
    api.post('/auth/login', `username=${username}&password=${password}`, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  
  logout: () => api.post('/auth/logout'),
  
  refresh: () => api.post('/auth/refresh'),
  
  getProfile: () => api.get('/auth/me'),
}

export const dashboardAPI = {
  getStatus: () => api.get('/dashboard/status'),
  getMetrics: () => api.get('/dashboard/metrics'),
  getSchedule: () => api.get('/dashboard/schedule'),
  getHealth: () => api.get('/dashboard/health'),
}

// Configuration API - DEPRECATED (removed from UI)
// We now use borg directly with per-repository passphrases
// Keeping this commented out for reference
/*
export const configAPI = {
  // List all configurations
  listConfigurations: () => api.get('/config/'),
  // Get default configuration
  getDefaultConfig: () => api.get('/config/default'),
  // Get specific configuration
  getConfiguration: (id: number) => api.get(`/config/${id}`),
  // Create new configuration
  createConfiguration: (data: { name: string; description?: string; content: string }) =>
    api.post('/config/', data),
  // Update configuration
  updateConfiguration: (id: number, data: { name?: string; description?: string; content?: string }) =>
    api.put(`/config/${id}`, data),
  // Delete configuration
  deleteConfiguration: (id: number) => api.delete(`/config/${id}`),
  // Set as default
  setDefaultConfiguration: (id: number) => api.post(`/config/${id}/set-default`),
  // Validate configuration content
  validateConfig: (config: string) => api.post('/config/validate', { content: config }),
  // Generate template using borgmatic CLI (recommended)
  generateTemplate: () => api.post('/config/generate-template'),
  // Get templates (deprecated - use generateTemplate instead)
  getTemplates: () => api.get('/config/templates'),

  // Legacy endpoints (keep for backward compatibility)
  getConfig: () => api.get('/config/current'),
  updateConfig: (config: string) => api.put('/config/update', { content: config }),
}
*/

export const backupAPI = {
  startBackup: (repository?: string) => api.post('/backup/start', { repository }),
  getStatus: (jobId: string) => api.get(`/backup/status/${jobId}`),
  getAllJobs: () => api.get('/backup/jobs'),
  cancelJob: (jobId: string) => api.post(`/backup/cancel/${jobId}`),
  getLogs: (jobId: string) => api.get(`/backup/logs/${jobId}`),
  // NEW: Stream logs incrementally
  streamLogs: (jobId: string, offset: number) =>
    api.get(`/backup/logs/${jobId}/stream`, { params: { offset } }),
}

export const archivesAPI = {
  listArchives: (repository: string) => api.get(`/archives/${repository}`),
  getArchiveInfo: (repository: string, archive: string) => 
    api.get(`/archives/${repository}/${archive}`),
  listContents: (repository: string, archive: string, path?: string) =>
    api.get(`/archives/${repository}/${archive}/contents`, { params: { path } }),
  deleteArchive: (repository: string, archive: string) =>
    api.delete(`/archives/${repository}/${archive}`),
}

export const restoreAPI = {
  previewRestore: (repository: string, archive: string, paths: string[]) =>
    api.post('/restore/preview', { repository, archive, paths }),
  startRestore: (repository: string, archive: string, paths: string[], destination: string) =>
    api.post('/restore/start', { repository, archive, paths, destination }),
}



export const logsAPI = {
  getLogs: (params: {
    log_type?: string;
    lines?: number;
    search?: string;
    level?: string;
    start_time?: string;
    end_time?: string;
  }) => api.get('/logs', { params }),
  getLogTypes: () => api.get('/logs/types'),
  getLogStats: (params: { log_type?: string; hours?: number }) => api.get('/logs/stats', { params }),
  clearLogs: (params: { log_type: string }) => api.delete('/logs/clear', { params }),
}

export const settingsAPI = {
  // System settings
  getSystemSettings: () => api.get('/settings/system'),
  updateSystemSettings: (settings: any) => api.put('/settings/system', settings),
  
  // User management
  getUsers: () => api.get('/settings/users'),
  createUser: (userData: any) => api.post('/settings/users', userData),
  updateUser: (userId: number, userData: any) => api.put(`/settings/users/${userId}`, userData),
  deleteUser: (userId: number) => api.delete(`/settings/users/${userId}`),
  resetUserPassword: (userId: number, newPassword: string) => 
    api.post(`/settings/users/${userId}/reset-password`, { new_password: newPassword }),
  
  // Profile management
  getProfile: () => api.get('/settings/profile'),
  updateProfile: (profileData: any) => api.put('/settings/profile', profileData),
  changePassword: (passwordData: any) => api.post('/settings/change-password', passwordData),
  
  // System maintenance
  cleanupSystem: () => api.post('/settings/system/cleanup'),
}

export const healthAPI = {
  getSystemHealth: () => api.get('/health/system'),
  getRepositoryHealth: () => api.get('/health/repositories'),
}

// Events API (Server-Sent Events)
export const eventsAPI = {
  streamEvents: () => {
    const token = localStorage.getItem('access_token')
    const url = `/api/events/stream${token ? `?token=${token}` : ''}`
    return new EventSource(url)
  },
  getConnectionCount: () => api.get('/events/connections'),
  sendBackupProgress: (data: any) => api.post('/events/backup-progress', data),
  sendSystemStatus: (data: any) => api.post('/events/system-status', data),
  sendLogUpdate: (data: any) => api.post('/events/log-update', data),
}

// Repositories API
export const repositoriesAPI = {
  getRepositories: () => api.get('/repositories/'),
  createRepository: (data: any) => api.post('/repositories/', data),
  getRepository: (id: number) => api.get(`/repositories/${id}`),
  updateRepository: (id: number, data: any) => api.put(`/repositories/${id}`, data),
  deleteRepository: (id: number) => api.delete(`/repositories/${id}`),
  checkRepository: (id: number) => api.post(`/repositories/${id}/check`),
  compactRepository: (id: number) => api.post(`/repositories/${id}/compact`),
  getRepositoryStats: (id: number) => api.get(`/repositories/${id}/stats`),
}

// SSH Keys API
export const sshKeysAPI = {
  // Single-key system
  getSystemKey: () => api.get('/ssh-keys/system-key'),
  generateSSHKey: (data: any) => api.post('/ssh-keys/generate', data),

  // Legacy multi-key endpoints (deprecated)
  getSSHKeys: () => api.get('/ssh-keys'),
  createSSHKey: (data: any) => api.post('/ssh-keys', data),
  quickSetup: (data: any) => api.post('/ssh-keys/quick-setup', data),
  getSSHKey: (id: number) => api.get(`/ssh-keys/${id}`),
  updateSSHKey: (id: number, data: any) => api.put(`/ssh-keys/${id}`, data),
  deleteSSHKey: (id: number) => api.delete(`/ssh-keys/${id}`),

  // Connection management
  deploySSHKey: (id: number, data: any) => api.post(`/ssh-keys/${id}/deploy`, data),
  testSSHConnection: (id: number, data: any) => api.post(`/ssh-keys/${id}/test-connection`, data),
  getSSHConnections: () => api.get('/ssh-keys/connections'),
}

// Schedule API
export const scheduleAPI = {
  getScheduledJobs: () => api.get('/schedule'),
  createScheduledJob: (data: any) => api.post('/schedule', data),
  getScheduledJob: (id: number) => api.get(`/schedule/${id}`),
  updateScheduledJob: (id: number, data: any) => api.put(`/schedule/${id}`, data),
  deleteScheduledJob: (id: number) => api.delete(`/schedule/${id}`),
  toggleScheduledJob: (id: number) => api.post(`/schedule/${id}/toggle`),
  runScheduledJobNow: (id: number) => api.post(`/schedule/${id}/run-now`),
  validateCronExpression: (data: any) => api.post('/schedule/validate-cron', data),
  getCronPresets: () => api.get('/schedule/cron-presets'),
  getUpcomingJobs: (hours?: number) => api.get('/schedule/upcoming-jobs', { params: { hours } }),
}

export default api 