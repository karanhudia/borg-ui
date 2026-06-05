import type { RcloneProvider } from '../../services/api'

const PROVIDER_AUTH_TYPE_ORDER: Record<RcloneProvider['auth_type'], number> = {
  none: 0,
  oauth_token: 1,
  access_key: 2,
  basic: 3,
  manual: 4,
}

export const rcloneProviderSearchText = (provider: RcloneProvider) =>
  [
    formatRcloneProviderLabel(provider.label),
    provider.label,
    provider.type,
    provider.description,
    provider.auth_type,
    provider.oauth_mode,
  ]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase()

export const formatRcloneProviderLabel = (label: string) => label.trim().replace(/\.$/, '')

export function sortRcloneProviders(providers: RcloneProvider[]) {
  return [...providers].sort((left, right) => {
    const leftRank = PROVIDER_AUTH_TYPE_ORDER[left.auth_type] ?? 99
    const rightRank = PROVIDER_AUTH_TYPE_ORDER[right.auth_type] ?? 99
    if (leftRank !== rightRank) return leftRank - rightRank
    if (left.type === 'custom') return 1
    if (right.type === 'custom') return -1
    return formatRcloneProviderLabel(left.label).localeCompare(
      formatRcloneProviderLabel(right.label)
    )
  })
}
