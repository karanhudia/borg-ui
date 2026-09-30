import type { AppTemplate } from '../../../services/api'
import type { BackupPlanScriptHook, SourceLocation } from '../../../types'
import { appExcludePatterns } from '../../../components/app-templates/appTemplates'
import type { WizardState } from '../types'

export interface AppTemplateChoice {
  template: AppTemplate
  /** Null for this server, otherwise the SSH connection the app runs on. */
  sshConnectionId: number | null
  root: string
  /** External folders (libraries) backed up alongside the app's folder. */
  extraPaths?: string[]
  excludes: string[]
  /** The created pre-backup check, when there is one. */
  scriptId: number | null
}

function sameMachine(location: SourceLocation, sshConnectionId: number | null): boolean {
  if (location.database || location.container) return false
  return sshConnectionId === null
    ? location.source_type === 'local'
    : location.source_type === 'remote' && location.source_ssh_connection_id === sshConnectionId
}

// scriptHooks wins over the legacy single-script fields once it has entries,
// so the check is added as a hook and any legacy scripts move along with it.
function withPreBackupHook(state: WizardState, scriptId: number): BackupPlanScriptHook[] {
  const hooks: BackupPlanScriptHook[] = [...(state.scriptHooks || [])]
  if (hooks.length === 0) {
    if (state.preBackupScriptId)
      hooks.push({
        script_id: state.preBackupScriptId,
        hook_type: 'pre-backup',
        execution_order: 1,
        enabled: true,
        parameter_values: state.preBackupScriptParameters,
      })
    if (state.postBackupScriptId)
      hooks.push({
        script_id: state.postBackupScriptId,
        hook_type: 'post-backup',
        execution_order: 1,
        enabled: true,
        parameter_values: state.postBackupScriptParameters,
      })
  }
  const order = hooks.filter((hook) => hook.hook_type === 'pre-backup').length + 1
  hooks.push({
    script_id: scriptId,
    hook_type: 'pre-backup',
    execution_order: order,
    enabled: true,
  })
  return hooks
}

/** The wizard state after adding an app: its folder, excludes, check script and schedule. */
export function applyAppTemplate(
  state: WizardState,
  choice: AppTemplateChoice
): Partial<WizardState> {
  const root = choice.root.trim()
  const added = [root, ...(choice.extraPaths ?? [])]
  const locations = [...(state.sourceLocations || [])]
  const index = locations.findIndex((location) => sameMachine(location, choice.sshConnectionId))
  if (index >= 0) {
    const paths = locations[index].paths
    locations[index] = {
      ...locations[index],
      paths: [...paths, ...added.filter((path) => !paths.includes(path))],
    }
  } else {
    locations.push({
      source_type: choice.sshConnectionId === null ? 'local' : 'remote',
      source_ssh_connection_id: choice.sshConnectionId,
      agent_machine_id: null,
      paths: added,
    })
  }

  const excludes = appExcludePatterns(root, choice.excludes)
  const first = locations[0]
  return {
    name: state.name.trim() || choice.template.name,
    sourceLocations: locations,
    sourceDirectories: locations.flatMap((location) => location.paths),
    sourceType: first.source_type,
    sourceSshConnectionId: first.source_ssh_connection_id ?? '',
    excludePatterns: [
      ...state.excludePatterns,
      ...excludes.filter((pattern) => !state.excludePatterns.includes(pattern)),
    ],
    ...(state.scheduleEnabled
      ? {}
      : { scheduleEnabled: true, cronExpression: choice.template.schedule_cron }),
    ...(choice.scriptId ? { scriptHooks: withPreBackupHook(state, choice.scriptId) } : {}),
  }
}
