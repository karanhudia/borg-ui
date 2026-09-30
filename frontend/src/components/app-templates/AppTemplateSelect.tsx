import { useTranslation } from 'react-i18next'

import type { AppTemplate } from '../../services/api'
import RichSelect, { type RichSelectOption } from '../shared/RichSelect'
import AppLogo from './AppLogo'

interface AppTemplateSelectProps {
  templates: AppTemplate[]
  value: AppTemplate | null
  onChange: (app: AppTemplate | null) => void
  disabled?: boolean
}

/** Searchable app picker with each app's logo; scales past a handful of apps. */
export default function AppTemplateSelect({
  templates,
  value,
  onChange,
  disabled,
}: AppTemplateSelectProps) {
  const { t } = useTranslation()
  const options: RichSelectOption[] = templates.map((template) => ({
    value: template.id,
    primary: template.name,
    secondary: template.description,
    icon: <AppLogo app={template} size={22} />,
  }))
  return (
    <RichSelect
      label={t('appTemplates.select.label')}
      value={value?.id ?? ''}
      placeholder={t('appTemplates.select.placeholder')}
      onChange={(id) => onChange(templates.find((template) => template.id === id) ?? null)}
      options={options}
      disabled={disabled}
      searchEnabled
      searchPlaceholder={t('appTemplates.select.search')}
      noResultsText={t('appTemplates.select.noResults')}
    />
  )
}
