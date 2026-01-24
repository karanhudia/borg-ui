export interface Repository {
    id: number
    name: string
    path: string
    repository_type?: 'local' | 'ssh'
    has_running_maintenance?: boolean
    host?: string
    port?: number
    username?: string
    [key: string]: unknown
}

export interface Archive {
    id: string
    archive: string
    name: string
    start: string
    time: string
}

export interface BackupJob {
    id: string | number
    repository: string
    status: 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled' | string
    started_at?: string
    completed_at?: string
    progress?: number
    total_files?: number
    processed_files?: number
    total_size?: string
    processed_size?: string
    current_file?: string
    message?: string
    error_message?: string
    triggered_by?: string
    schedule_id?: number | null
    has_logs?: boolean
    progress_details?: {
        original_size: number
        compressed_size: number
        deduplicated_size: number
        nfiles: number
        current_file: string
        backup_speed?: number
        total_expected_size?: number
        estimated_time_remaining?: number
        [key: string]: unknown
    }
}

export interface SystemMetrics {
    cpu_usage: number
    memory_total: number
    memory_available: number
    memory_usage: number
    disk_total: number
    disk_free: number
    disk_usage: number
}

export interface DashboardStatus {
    system_metrics?: SystemMetrics
    recent_jobs?: BackupJob[]
}
