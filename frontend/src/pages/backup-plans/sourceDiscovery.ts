import type { SourceDiscoveryDatabase, SourceDiscoveryScriptTemplate } from '../../services/api'

export interface DatabaseDiscoverySelection {
  database: SourceDiscoveryDatabase
  sourceDirectories: string[]
  preBackupScript: SourceDiscoveryScriptTemplate
  postBackupScript: SourceDiscoveryScriptTemplate
}
