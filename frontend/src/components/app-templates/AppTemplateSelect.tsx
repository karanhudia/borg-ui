import { FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { AppTemplate } from '../../services/api'
import RichSelect, { type RichSelectOption } from '../shared/RichSelect'
import AppLogo from './AppLogo'

const NONE = 'none'

interface AppTemplateSelectProps {
  templates: AppTemplate[]
  value: AppTemplate | null
  onChange: (app: AppTemplate | null) => void
  /** Offer "Something else" (plain folders) as the first choice. */
  allowNone?: boolean
  disabled?: boolean
}

/** Searchable app picker with each app's logo; scales past a handful of apps. */
export default function AppTemplateSelect({
  templates,
  value,
  onChange,
  allowNone = false,
  disabled,
}: AppTemplateSelectProps) {
  const { t } = useTranslation()
  const options: RichSelectOption[] = [
    ...(allowNone
      ? [
          {
            value: NONE,
            primary: t('appTemplates.select.none'),
            secondary: t('appTemplates.select.noneDesc'),
            icon: <FolderOpen size={18} />,
          },
        ]
      : []),
    ...templates.map((template) => ({
      value: template.id,
      primary: template.name,
      secondary: template.description,
      icon: <AppLogo app={template} size={22} />,
      group: allowNone ? t('appTemplates.select.apps') : undefined,
    })),
  ]
  return (
    <RichSelect
      label={t('appTemplates.select.label')}
      value={value?.id ?? (allowNone ? NONE : '')}
      onChange={(id) => onChange(templates.find((template) => template.id === id) ?? null)}
      options={options}
      disabled={disabled}
      searchEnabled
      searchPlaceholder={t('appTemplates.select.search')}
      noResultsText={t('appTemplates.select.noResults')}
    />
  )
}
