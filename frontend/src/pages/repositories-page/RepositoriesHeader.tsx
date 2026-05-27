import Add from '@mui/icons-material/Add'
import FileUpload from '@mui/icons-material/FileUpload'
import { Button, Stack } from '@mui/material'
import { useTranslation } from 'react-i18next'
import PageHeader from '../../components/PageHeader'
import type { Repository } from './types'

interface RepositoriesHeaderProps {
  canManageRepositoriesGlobally: boolean
  onOpenWizard: (mode: 'create' | 'edit' | 'import', repository?: Repository) => void
}

export function RepositoriesHeader({
  canManageRepositoriesGlobally,
  onOpenWizard,
}: RepositoriesHeaderProps) {
  const { t } = useTranslation()

  return (
    <PageHeader
      title={t('repositories.title')}
      subtitle={t('repositories.subtitle')}
      actions={
        canManageRepositoriesGlobally ? (
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => onOpenWizard('create')}
              sx={{
                width: { xs: '100%', md: 'auto' },
                boxShadow: '0 2px 8px rgba(37,99,235,0.3)',
              }}
            >
              {t('repositories.createRepository')}
            </Button>
            <Button
              variant="outlined"
              startIcon={<FileUpload />}
              onClick={() => onOpenWizard('import')}
              sx={{ width: { xs: '100%', md: 'auto' } }}
            >
              {t('repositories.importExisting')}
            </Button>
          </Stack>
        ) : null
      }
    />
  )
}
