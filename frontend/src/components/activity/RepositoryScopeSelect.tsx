import { Database, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import RichSelect from '../shared/RichSelect'
import { repositoriesAPI } from '../../services/api'
import type { Repository } from '@/types'

interface RepositoryScopeSelectProps {
  value: number | null
}

// The way into (and between) repository-scoped activity views. "All
// repositories" is the global ledger; any repository opens its own
// Operations view at /activity?repository_id=.
export default function RepositoryScopeSelect({ value }: RepositoryScopeSelectProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories: Repository[] = data?.data?.repositories ?? []

  return (
    <RichSelect
      label={t('activity.repositoryScope.label')}
      value={value != null ? String(value) : 'all'}
      onChange={(next) =>
        navigate(next === 'all' ? '/activity' : `/activity?repository_id=${next}`)
      }
      searchEnabled={repositories.length > 8}
      options={[
        {
          value: 'all',
          primary: t('activity.repositoryScope.all'),
          icon: <Layers size={16} />,
        },
        ...repositories.map((repo) => ({
          value: String(repo.id),
          primary: repo.name,
          secondary: repo.path,
          icon: <Database size={16} />,
        })),
      ]}
    />
  )
}
