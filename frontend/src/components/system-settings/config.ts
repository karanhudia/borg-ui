import type { TFunction } from 'i18next'

import type { AuthConfigResponse } from '../../services/api'
import type { SectionTabConfig } from './types'

export const buildProxyAuthHeaderRows = (
  proxyAuthConfig?: AuthConfigResponse
): Array<[string, string | null | undefined]> => [
  ['systemSettings.proxyAuthUsernameHeader', proxyAuthConfig?.proxy_auth_header],
  ['systemSettings.proxyAuthRoleHeader', proxyAuthConfig?.proxy_auth_role_header],
  [
    'systemSettings.proxyAuthAllRepositoriesRoleHeader',
    proxyAuthConfig?.proxy_auth_all_repositories_role_header,
  ],
  ['systemSettings.proxyAuthEmailHeader', proxyAuthConfig?.proxy_auth_email_header],
  ['systemSettings.proxyAuthFullNameHeader', proxyAuthConfig?.proxy_auth_full_name_header],
]

export const buildSectionTabs = (t: TFunction): SectionTabConfig[] => [
  {
    label: t('systemSettings.operationTimeoutsTitle'),
    description: t('systemSettings.operationTimeoutsDescription'),
  },
  {
    label: t('systemSettings.repositoryMonitoringTitle'),
    description: t('systemSettings.repositoryMonitoringDescription'),
  },
  {
    label: t('systemSettings.metricsAccessTitle'),
    description: t('systemSettings.metricsAccessDescription'),
  },
  {
    label: t('systemSettings.archiveBrowsingLimitsTitle'),
    description: t('systemSettings.archiveBrowsingLimitsDescription'),
  },
  {
    label: t('systemSettings.proxyAuthTitle'),
    description: t('systemSettings.proxyAuthDescription'),
  },
  {
    label: t('systemSettings.oidcTitle'),
    description: t('systemSettings.oidcDescription'),
  },
]
