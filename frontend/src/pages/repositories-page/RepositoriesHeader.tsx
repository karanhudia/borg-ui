import { Add, FileUpload } from '@mui/icons-material'
import { Box, Button, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
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
    <Box sx={{ mb: 3 }}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', md: 'flex-start' },
          gap: 2,
          mb: 2,
        }}
      >
        <Box sx={{ flex: 1, mr: { md: 2 } }}>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            {t('repositories.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            {t('repositories.subtitle')}
          </Typography>
        </Box>
        {canManageRepositoriesGlobally && (
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
        )}
      </Box>
    </Box>
  )
}
