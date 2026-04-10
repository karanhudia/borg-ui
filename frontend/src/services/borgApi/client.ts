/**
 * BorgApiClient — pure class, no React dependency.
 *
 * This is the ONLY place in the codebase where API URL routing based on
 * borg version lives. All components call methods on this class; none of
 * them construct URLs or check borg_version directly.
 *
 * v1 repos  →  /api/...       (existing routes, unchanged)
 * v2 repos  →  /api/v2/...    (new Borg 2 routes)
 */

import axios from 'axios'
import { BASE_PATH } from '@/utils/basePath'
import type { Repository } from '@/types'
import { isV2Repo } from '@/utils/repoCapabilities'
import { buildDownloadUrl } from '@/utils/downloadUrl'

// Re-use the same axios instance (with auth interceptors) from api.ts
// by importing only the create pattern — auth token injection is handled
// by the global interceptor already set up in api.ts.
export const httpClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || `${BASE_PATH}/api`,
  headers: { 'Content-Type': 'application/json' },
})

// Mirror the auth interceptor so this client also attaches tokens
httpClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

httpClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      error.config?.url !== '/auth/login' &&
      error.config?.url !== '/auth/config'
    ) {
      localStorage.removeItem('access_token')
      window.location.href = `${BASE_PATH}/login`
    }
    return Promise.reject(error)
  }
)

export type { Repository } from '@/types'

export interface BackupOptions {
  archive_name?: string
}

export interface PruneOptions {
  keep_hourly?: number
  keep_daily?: number
  keep_weekly?: number
  keep_monthly?: number
  keep_quarterly?: number
  keep_yearly?: number
  dry_run?: boolean
}

export class BorgApiClient {
  /** Version-aware URL prefix — the single routing decision point. */
  private readonly v: string

  /** Repository ID, carried for convenience on all calls. */
  readonly repoId: number
  private readonly repoPath?: string

  constructor(repo: Repository) {
    this.repoId = repo.id
    this.repoPath = typeof repo.path === 'string' ? repo.path : undefined
    this.v = isV2Repo(repo) ? '/v2' : ''
  }

  // ── Pre-creation (no repo ID yet) ────────────────────────────────────────

  static createRepository(data: Omit<Repository, 'id'>) {
    const v = isV2Repo(data) ? '/v2' : ''
    return httpClient.post(`${v}/repositories/`, data)
  }

  static importRepository(data: Omit<Repository, 'id'>) {
    const v = isV2Repo(data) ? '/v2' : ''
    return httpClient.post(`${v}/repositories/import`, data)
  }

  private get repoBase() {
    return `${this.v}/repositories/${this.repoId}`
  }

  // ── Repository info ──────────────────────────────────────────────────────

  getInfo() {
    return httpClient.get(`${this.repoBase}/info`)
  }

  // ── Archives ─────────────────────────────────────────────────────────────

  listArchives() {
    return httpClient.get(`${this.repoBase}/archives`)
  }

  getArchiveInfo(archiveId: string, includeFiles = false, fileLimit = 1000) {
    return httpClient.get(`${this.v}/archives/${archiveId}/info`, {
      params: { repository: this.repoId, include_files: includeFiles, file_limit: fileLimit },
    })
  }

  getArchiveContents(archiveId: string, archiveName: string, path = '') {
    if (this.v === '/v2') {
      return httpClient.get(`/v2/archives/${archiveId}/contents`, {
        params: { repository: this.repoId, path },
      })
    }
    // v1: use the browse endpoint (cached, path-filtered) — needs archive NAME not hex ID
    return httpClient.get(`/browse/${this.repoId}/${archiveName}`, {
      params: { path },
    })
  }

  deleteArchive(archiveId: string) {
    return httpClient.delete(`${this.v}/archives/${archiveId}`, {
      params: { repository: this.repoId },
    })
  }

  getDeleteJobStatus(jobId: number) {
    return httpClient.get(`${this.v}/archives/delete-jobs/${jobId}`)
  }

  getDownloadUrl(archiveId: string, filePath: string) {
    return buildDownloadUrl(`${this.v}/archives/download`, {
      repository: this.repoId,
      archive: archiveId,
      file_path: filePath,
    })
  }

  // ── Backup operations ────────────────────────────────────────────────────

  runBackup(options: BackupOptions = {}) {
    if (this.v === '/v2') {
      return httpClient.post('/v2/backup/run', {
        repository_id: this.repoId,
        ...options,
      })
    }

    return httpClient.post('/backup/start', {
      repository: this.repoPath,
      ...options,
    })
  }

  pruneArchives(options: PruneOptions = {}) {
    if (this.v === '/v2') {
      return httpClient.post(`/v2/backup/prune`, { repository_id: this.repoId, ...options })
    }
    return httpClient.post(`/repositories/${this.repoId}/prune`, options)
  }

  compact() {
    if (this.v === '/v2') {
      return httpClient.post(`/v2/backup/compact`, { repository_id: this.repoId })
    }
    return httpClient.post(`/repositories/${this.repoId}/compact`)
  }

  checkRepository(maxDuration?: number) {
    if (this.v === '/v2') {
      return httpClient.post(`/v2/backup/check`, {
        repository_id: this.repoId,
        ...(maxDuration !== undefined && { max_duration: maxDuration }),
      })
    }
    return httpClient.post(`/repositories/${this.repoId}/check`, {
      ...(maxDuration !== undefined && { max_duration: maxDuration }),
    })
  }
}
