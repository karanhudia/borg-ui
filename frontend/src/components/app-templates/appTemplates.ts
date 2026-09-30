import { useQuery } from '@tanstack/react-query'

import { sourceDiscoveryAPI, type AppTemplate } from '../../services/api'

const APP_ROOT_PLACEHOLDER = '__APP_ROOT__'

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

function trimRoot(root: string): string {
  return root.trim().replace(/\/+$/, '') || '/'
}

/** Absolute exclude patterns for the chosen rebuildable folders under the app's root. */
export function appExcludePatterns(root: string, excludes: string[]): string[] {
  const base = trimRoot(root)
  return excludes.map((path) => `${base === '/' ? '' : base}/${path}`)
}

export function defaultAppExcludes(template: AppTemplate): string[] {
  return template.excludes.filter((exclude) => exclude.default).map((exclude) => exclude.path)
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`
}

/** The template's pre-backup script with the app's root folder filled in. */
export function renderAppScript(template: AppTemplate, root: string): string | null {
  const script = template.pre_backup_script
  if (!script) return null
  return script.content.split(APP_ROOT_PLACEHOLDER).join(shellQuote(trimRoot(root)))
}

/**
 * The compose line that makes a host folder readable to Borg UI in Docker,
 * mounted where the path mapping looks for it (/local + host path).
 */
export function mountHint(hostPath: string): string {
  const path = trimRoot(hostPath)
  return `- ${path}:/local${path}:ro`
}
