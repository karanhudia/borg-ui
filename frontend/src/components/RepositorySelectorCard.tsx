import {
  Card,
  CardContent,
  Stack,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material'
import { Database } from 'lucide-react'

interface Repository {
  id: number
  name: string
  path: string
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
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
          <Database size={20} color="#2e7d32" />
          <Typography variant="h6" fontWeight={600}>
            Select Repository
          </Typography>
        </Stack>
        <FormControl fullWidth sx={{ minWidth: { xs: '100%', sm: 300 } }}>
          <InputLabel id="repository-select-label" sx={{ color: 'text.primary' }}>
            Repository
          </InputLabel>
          <Select
            labelId="repository-select-label"
            value={selectedRepositoryId || ''}
            onChange={(e) => onRepositoryChange(e.target.value as number)}
            label="Repository"
            disabled={loading}
            sx={{ height: { xs: 48, sm: 56 } }}
          >
            <MenuItem value="" disabled>
              {loading ? 'Loading repositories...' : 'Select a repository...'}
            </MenuItem>
            {repositories.map((repo) => (
              <MenuItem key={repo.id} value={repo.id}>
                {repo.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </CardContent>
    </Card>
  )
}
