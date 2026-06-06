import { CheckCircle2, CircleAlert, Monitor, Server, WifiOff } from 'lucide-react'
import { getLocalBackendTarget } from '@/services/remoteBackends/storage'
import type { BackendTarget, RemoteBackendClient } from '@/services/remoteBackends/types'

type Translate = (key: string, options?: Record<string, unknown>) => string

export function buildBackendTargets(
  activeTarget: BackendTarget,
  clients: RemoteBackendClient[],
  t: Translate
): BackendTarget[] {
  const localTarget = getLocalBackendTarget()
  return [
    {
      ...localTarget,
      name: t('remoteClients.switcher.localName'),
      apiBaseUrl: activeTarget.kind === 'local' ? activeTarget.apiBaseUrl : localTarget.apiBaseUrl,
      health: {
        ...localTarget.health,
        compatibilityMessage: t('remoteClients.switcher.localCompatibility'),
      },
    },
    ...clients,
  ]
}

export function getBackendTargetName(target: BackendTarget, t: Translate): string {
  return target.kind === 'local' ? t('remoteClients.switcher.localName') : target.name
}

export function isBackendTargetDisabled(target: BackendTarget): boolean {
  return target.kind === 'remote' && target.health.compatibility === 'incompatible'
}

export function getBackendTargetStatus(target: BackendTarget, t: Translate) {
  if (target.kind === 'local') {
    return {
      label: t('remoteClients.labels.local'),
      color: 'default' as const,
      icon: <Monitor size={14} />,
      helper: t('remoteClients.switcher.localHelper'),
    }
  }

  if (target.health.compatibility === 'incompatible') {
    return {
      label: t('remoteClients.status.incompatible'),
      color: 'warning' as const,
      icon: <CircleAlert size={14} />,
      helper: target.health.compatibilityMessage || t('remoteClients.switcher.versionMismatch'),
    }
  }

  if (target.health.status === 'online') {
    return {
      label: t('remoteClients.status.online'),
      color: 'success' as const,
      icon: <CheckCircle2 size={14} />,
      helper: target.health.appVersion
        ? t('remoteClients.switcher.versionHelper', { version: target.health.appVersion })
        : t('remoteClients.switcher.remoteHelper'),
    }
  }

  if (target.health.status === 'offline') {
    return {
      label: t('remoteClients.status.offline'),
      color: 'error' as const,
      icon: <WifiOff size={14} />,
      helper: target.health.error || t('remoteClients.switcher.remoteUnavailable'),
    }
  }

  return {
    label: t('remoteClients.labels.remoteClient'),
    color: 'default' as const,
    icon: <Server size={14} />,
    helper: t('remoteClients.switcher.remoteHelper'),
  }
}
