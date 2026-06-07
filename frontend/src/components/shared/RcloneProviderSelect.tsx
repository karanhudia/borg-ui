import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { RcloneProvider } from '../../services/api'
import RichSelect, { type RichSelectOption } from './RichSelect'
import RcloneProviderIcon from './RcloneProviderIcon'
import {
  formatRcloneProviderLabel,
  rcloneProviderSearchText,
  sortRcloneProviders,
} from './rcloneProviderSelectUtils'

interface RcloneProviderSelectProps {
  value: string
  onChange: (providerType: string) => void
  providers: RcloneProvider[]
  label: string
  disabled?: boolean
  required?: boolean
}

export default function RcloneProviderSelect({
  value,
  onChange,
  providers,
  label,
  disabled,
  required,
}: RcloneProviderSelectProps) {
  const { t } = useTranslation()
  const sortedProviders = useMemo(() => sortRcloneProviders(providers), [providers])
  const selectedProvider =
    sortedProviders.find((provider) => provider.type === value) ?? sortedProviders[0] ?? null
  const options = useMemo<RichSelectOption[]>(() => {
    return sortedProviders.map((provider) => ({
      value: provider.type,
      primary: formatRcloneProviderLabel(provider.label),
      secondary: provider.type,
      icon: <RcloneProviderIcon provider={provider.type} size={32} iconSize={16} />,
      iconFrame: false,
      group: t(`wizard.location.rcloneAuthTypes.${provider.auth_type}`, {
        defaultValue: provider.auth_type,
      }),
      searchText: rcloneProviderSearchText(provider),
    }))
  }, [sortedProviders, t])

  return (
    <RichSelect
      value={selectedProvider?.type ?? ''}
      onChange={onChange}
      options={options}
      label={label}
      disabled={disabled}
      required={required}
      searchEnabled
      searchPlaceholder={t('wizard.location.rcloneProviderSearchPlaceholder', {
        defaultValue: 'Search providers',
      })}
      noResultsText={t('wizard.location.rcloneProviderSearchNoResults', {
        defaultValue: 'No providers found',
      })}
    />
  )
}
