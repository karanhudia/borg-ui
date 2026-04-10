import { useTranslation } from 'react-i18next'
import { Repository } from '../types'
import RepoSelect from './RepoSelect'
import { SxProps, Theme } from '@mui/material'

interface RepositorySelectorCardProps {
  title?: string
  repositories: Repository[]
  value: number | string | null
  onChange: (value: number | string) => void
  loading?: boolean
  valueKey?: 'id' | 'path'
  sx?: SxProps<Theme>
}

export default function RepositorySelectorCard({
  repositories,
  value,
  onChange,
  loading = false,
  valueKey = 'id',
  sx,
}: RepositorySelectorCardProps) {
  const { t } = useTranslation()
  return (
    <RepoSelect
      repositories={repositories}
      value={value ?? ''}
      onChange={onChange}
      loading={loading}
      valueKey={valueKey}
      label={t('common.repository')}
      loadingLabel={t('repositorySelectorCard.loading')}
      placeholderLabel={t('repositorySelectorCard.placeholder')}
      maintenanceLabel={t('repositorySelectorCard.maintenanceRunning')}
      sx={{ mb: 3, ...sx }}
    />
  )
}
