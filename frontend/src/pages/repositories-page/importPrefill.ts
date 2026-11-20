import type { RepositoryWizardInitialValues } from '../../components/RepositoryWizard'

/** Reads the import link the MCP `import_repository` tool hands the user
 *  (spec 2026-11-14-mcp-server 5.9). Unknown or malformed values are ignored. */
export function parseImportPrefill(params: URLSearchParams): RepositoryWizardInitialValues | null {
  if (params.get('import') !== '1') return null
  const values: RepositoryWizardInitialValues = {}
  const name = params.get('name')
  const path = params.get('path')
  if (name) values.name = name
  if (path) values.path = path
  const version = params.get('borg_version')
  if (version === '1' || version === '2') values.borgVersion = Number(version) as 1 | 2
  const connection = Number(params.get('connection_id'))
  if (Number.isInteger(connection) && connection > 0) {
    values.repositoryLocation = 'ssh'
    values.repoSshConnectionId = connection
  }
  return values
}

export const IMPORT_PREFILL_PARAMS = ['import', 'name', 'path', 'borg_version', 'connection_id']
