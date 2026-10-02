import { useQuery } from '@tanstack/react-query'

import { sourceDiscoveryAPI, type AppTemplate } from '../../services/api'

const APP_ROOT_PLACEHOLDER = '__APP_ROOT__'
const CONTAINER_PLACEHOLDER = '__CONTAINER__'

/** Where to look for the app: this server, or an SSH machine. Agents can't be scanned. */
export type AppScanTarget =
  | { source_type: 'local'; source_ssh_connection_id: null }
  | { source_type: 'remote'; source_ssh_connection_id: number }

export function useAppTemplates() {
  const { data, isLoading } = useQuery({
    queryKey: ['app-templates'],
    queryFn: () => sourceDiscoveryAPI.appTemplates(),
    staleTime: Infinity,
  })
  return { templates: data?.data.templates ?? [], loading: isLoading }
}

export function useAppDetection(template: AppTemplate | null, target: AppScanTarget | null) {
  const query = useQuery({
    queryKey: ['app-detect', target?.source_type, target?.source_ssh_connection_id],
    queryFn: () => sourceDiscoveryAPI.detectApps(target as AppScanTarget),
    enabled: Boolean(template && target),
    staleTime: 60_000,
    retry: false,
  })
  const response = query.data?.data
  return {
    detection: response?.detections.find((item) => item.template_id === template?.id) ?? null,
    warning: response?.warnings[0]?.message ?? null,
    scanning: query.isFetching,
    rescan: () => void query.refetch(),
  }
}

export function trimRoot(root: string): string {
  return root.trim().replace(/\/+$/, '') || '/'
}

/** Absolute exclude patterns for the chosen rebuildable folders under the app's root. */
export function appExcludePatterns(root: string, excludes: string[]): string[] {
  const base = trimRoot(root)
  return excludes.map((path) => `${base === '/' ? '' : base}/${path}`)
}

export function defaultAppExcludes(template: AppTemplate): string[] {
  return template.folders
    .filter((folder) => folder.role === 'rebuildable')
    .map((folder) => folder.path)
}

/** Size and newest file of each folder the template describes, under the chosen root. */
export function useAppInspection(
  template: AppTemplate | null,
  target: AppScanTarget | null,
  root: string,
  extraPaths: string[] = []
) {
  const path = root.trim()
  const query = useQuery({
    queryKey: [
      'app-inspect',
      template?.id,
      target?.source_type,
      target?.source_ssh_connection_id,
      path,
      extraPaths,
    ],
    queryFn: () =>
      sourceDiscoveryAPI.inspectApp({
        template_id: (template as AppTemplate).id,
        ...(target as AppScanTarget),
        path,
        extra_paths: extraPaths,
      }),
    enabled: Boolean(template && target && path.startsWith('/')),
    staleTime: 60_000,
    retry: false,
  })
  const data = query.data?.data
  return {
    // Sizes only mean something when the folder could be opened.
    stats: data?.root_status === 'ok' ? data.folders : null,
    rootStatus: data?.root_status ?? null,
    user: data?.user ?? null,
    measuring: query.isFetching,
  }
}

/** True when the newest file is older than the folder allows, or there is none. */
export function isStale(
  latestModifiedAt: string | null,
  staleAfterHours: number | null,
  now: number = Date.now()
): boolean {
  if (staleAfterHours === null) return false
  if (!latestModifiedAt) return true
  return now - new Date(latestModifiedAt).getTime() > staleAfterHours * 3_600_000
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`
}

/**
 * The template's pre-backup script with the app's root folder and container
 * filled in. The container is '' when the folder was picked by hand.
 */
export function renderAppScript(
  template: AppTemplate,
  root: string,
  container: string = ''
): string | null {
  const script = template.pre_backup_script
  if (!script) return null
  return script.content
    .split(APP_ROOT_PLACEHOLDER)
    .join(shellQuote(trimRoot(root)))
    .split(CONTAINER_PLACEHOLDER)
    .join(shellQuote(container))
}

/**
 * The compose line that makes a host folder readable to Borg UI in Docker,
 * mounted where the path mapping looks for it (/local + host path).
 */
export function mountHint(hostPath: string): string {
  const path = trimRoot(hostPath)
  return `- ${path}:/local${path}:ro`
}

/**
 * Commands that let `user` read `path` and everything Immich adds to it later,
 * plus traverse (not list) each parent folder.
 */
export function readAccessCommands(user: string, path: string): string {
  const parts = trimRoot(path).split('/').filter(Boolean)
  const parents = parts.slice(0, -1).map((_, index) => `/${parts.slice(0, index + 1).join('/')}`)
  const quote = (value: string) => shellQuote(value)
  return [
    // A folder right under / has no parents to open up.
    ...(parents.length ? [`sudo setfacl -m u:${user}:x ${parents.map(quote).join(' ')}`] : []),
    `sudo setfacl -R -m u:${user}:rX,d:u:${user}:rX ${quote(trimRoot(path))}`,
  ].join('\n')
}

/**
 * The template's pre-backup check guards its database dumps; with those not
 * backed up it would only stop backups for a folder the user left out.
 */
export function checksBackedUpDumps(template: AppTemplate, excludes: string[]): boolean {
  return template.folders
    .filter((folder) => folder.role === 'database')
    .every((folder) => !excludes.includes(folder.path))
}
