import { useTranslation } from 'react-i18next'
import {
  Card,
  CardContent,
  Stack,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Box,
} from '@mui/material'
import { Database } from 'lucide-react'

interface Repository {
  id: number
  name: string
  path: string
  has_running_maintenance?: boolean
}

interface RepositorySelectorCardProps {
  repositories: Repository[]
  selectedRepositoryId: number | null
  onRepositoryChange: (repositoryId: number) => void
  loading?: boolean
}

export default function RepositorySelectorCard({
  repositories,
  selectedRepositoryId,
  onRepositoryChange,
  loading = false,
}: RepositorySelectorCardProps) {
  const { t } = useTranslation()
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
          <Database size={20} color="#2e7d32" />
          <Typography variant="h6" fontWeight={600}>
            {t('repositorySelectorCard.title')}
          </Typography>
        </Stack>
        <FormControl fullWidth sx={{ minWidth: { xs: '100%', sm: 300 } }}>
          <InputLabel id="repository-select-label" sx={{ color: 'text.primary' }}>
            {t('common.repository')}
          </InputLabel>
          <Select
            labelId="repository-select-label"
            value={selectedRepositoryId || ''}
            onChange={(e) => onRepositoryChange(e.target.value as number)}
            label={t('common.repository')}
            disabled={loading}
            sx={{ height: { xs: 48, sm: 56 } }}
          >
            <MenuItem value="" disabled>
              {loading ? t('repositorySelectorCard.loading') : t('repositorySelectorCard.placeholder')}
            </MenuItem>
            {repositories.map((repo) => (
              <MenuItem key={repo.id} value={repo.id} disabled={repo.has_running_maintenance}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Database size={16} />
                  <Box>
                    <Typography variant="body2" fontWeight={500}>
                      {repo.name}
                      {repo.has_running_maintenance && (
                        <Typography
                          component="span"
                          variant="caption"
                          color="warning.main"
                          sx={{ ml: 1 }}
                        >
                          {t('repositorySelectorCard.maintenanceRunning')}
                        </Typography>
                      )}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ fontFamily: 'monospace' }}
                    >
                      {repo.path}
                    </Typography>
                  </Box>
                </Stack>
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </CardContent>
    </Card>
  )
}
