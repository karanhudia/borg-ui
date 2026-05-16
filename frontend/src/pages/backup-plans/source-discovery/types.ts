export interface SourceDiscoveryType {
  id: 'paths' | 'database' | 'container' | string
  label: string
  description: string
  enabled: boolean
  unavailable_reason?: string | null
}

export interface DatabaseDiscoveryTarget {
  id: string
  engine: string
  engine_label: string
  display_name: string
  status: 'detected' | 'template'
  confidence: 'high' | 'medium' | 'template'
  service_name: string
  source_directories: string[]
  warnings: string[]
  pre_backup_script: string
  post_backup_script: string
  script_name_base: string
  documentation_url: string
}

export interface DatabaseDiscoveryResponse {
  source_types: SourceDiscoveryType[]
  databases: DatabaseDiscoveryTarget[]
  templates: DatabaseDiscoveryTarget[]
}

export interface AppliedDatabaseSource {
  sourceType: 'local'
  sourceSshConnectionId: ''
  sourceDirectories: string[]
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  preBackupScriptParameters: Record<string, string>
  postBackupScriptParameters: Record<string, string>
}
