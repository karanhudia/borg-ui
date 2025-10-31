import { FormControl, InputLabel, Select, MenuItem, Box, Typography, Chip } from '@mui/material'
import { HardDrive, Wifi } from 'lucide-react'

interface Repository {
  id: number
  name: string
  path: string
  repository_type: 'local' | 'ssh'
}

interface RepositorySelectorProps {
  repositories: Repository[]
  selectedRepositoryId: number | null
  onRepositoryChange: (repositoryId: number) => void
  loading?: boolean
}

export default function RepositorySelector({
  repositories,
  selectedRepositoryId,
  onRepositoryChange,
  loading = false
}: RepositorySelectorProps) {
  return (
    <FormControl fullWidth size="small">
      <InputLabel>Repository</InputLabel>
      <Select
        value={selectedRepositoryId || ''}
        onChange={(e) => onRepositoryChange(e.target.value as number)}
        label="Repository"
        disabled={loading || repositories.length === 0}
      >
        {repositories.length === 0 ? (
          <MenuItem disabled>
            <Typography variant="body2" color="text.secondary">
              No repositories available
            </Typography>
          </MenuItem>
        ) : (
          repositories.map((repo) => (
            <MenuItem key={repo.id} value={repo.id}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                {repo.repository_type === 'local' ? (
                  <HardDrive size={16} />
                ) : (
                  <Wifi size={16} />
                )}
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {repo.name}
                </Typography>
                <Chip
                  label={repo.repository_type}
                  size="small"
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              </Box>
            </MenuItem>
          ))
        )}
      </Select>
    </FormControl>
  )
}
