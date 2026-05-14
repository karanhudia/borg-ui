import React from 'react'
import { useTranslation } from 'react-i18next'
import { Autocomplete, TextField, Box, Typography, Stack, IconButton, Tooltip } from '@mui/material'
import { ChevronUp, ChevronDown, X } from 'lucide-react'
import { Repository } from '../types'
import RepoMenuItem from './RepoMenuItem'
import { getRepoCapabilities } from '../utils/repoCapabilities'

interface MultiRepositorySelectorProps {
  repositories: Repository[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
  label?: string
  helperText?: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
  size?: 'small' | 'medium'
  allowReorder?: boolean
  error?: boolean
  filterMode?: 'observe' | null // Exclude repositories with this mode
  getOptionDisabled?: (repo: Repository) => boolean
}

/**
 * Reusable multi-repository selector with chip-based UI
 * - Shows repository name and path in dropdown
 * - Selected items displayed as chips with path tooltip
 * - Optional reordering support for scheduled backups
 * - Used in both Notifications and Schedule pages
 */
export const MultiRepositorySelector: React.FC<MultiRepositorySelectorProps> = ({
  repositories,
  selectedIds,
  onChange,
  label = 'Repositories',
  helperText,
  placeholder = 'Select repositories...',
  required = false,
  disabled = false,
  size = 'medium',
  allowReorder = false,
  error = false,
  filterMode = null,
  getOptionDisabled,
}) => {
  const { t } = useTranslation()
  // Track whether user has interacted with the field
  const [touched, setTouched] = React.useState(false)

  // Ensure repositories is always an array
  const safeRepositories = Array.isArray(repositories) ? repositories : []

  // Filter repositories if needed (filterMode='observe' excludes repos that can't back up)
  const availableRepos = filterMode
    ? safeRepositories.filter((repo) => getRepoCapabilities(repo).canBackup)
    : safeRepositories

  // Get selected repositories in order
  const selectedRepos = selectedIds
    .map((id) => availableRepos.find((r) => r.id === id))
    .filter(Boolean) as Repository[]

  const handleMoveUp = (index: number) => {
    if (index === 0) return
    const newIds = [...selectedIds]
    ;[newIds[index - 1], newIds[index]] = [newIds[index], newIds[index - 1]]
    onChange(newIds)
  }

  const handleMoveDown = (index: number) => {
    if (index === selectedIds.length - 1) return
    const newIds = [...selectedIds]
    ;[newIds[index], newIds[index + 1]] = [newIds[index + 1], newIds[index]]
    onChange(newIds)
  }

  const handleRemove = (repoId: number) => {
    onChange(selectedIds.filter((id) => id !== repoId))
  }

  return (
    <Box>
      <Autocomplete
        multiple
        disabled={disabled}
        options={availableRepos}
        value={selectedRepos}
        onOpen={() => setTouched(true)}
        onChange={(_, newValue) => {
          setTouched(true)
          // Preserve order for existing items, add new items at end
          const newIds = newValue.map((r) => r.id)
          // Use Set to enforce uniqueness while preserving order
          const uniqueIds = Array.from(new Set(newIds))
          onChange(uniqueIds)
        }}
        getOptionLabel={(option) => option.name}
        getOptionDisabled={getOptionDisabled}
        isOptionEqualToValue={(option, value) => option.id === value.id}
        renderOption={(props, option) => (
          <Box component="li" {...props} sx={{ py: 0.5 }}>
            <RepoMenuItem
              name={option.name}
              path={option.path}
              borgVersion={option.borg_version}
              mode={option.mode as 'full' | 'observe' | undefined}
              hasRunningMaintenance={option.has_running_maintenance}
            />
          </Box>
        )}
        renderTags={() => null} // We render tags manually below
        renderInput={(params) => (
          <TextField
            {...params}
            label={label}
            placeholder={
              selectedIds.length === 0 ? placeholder : t('multiRepositorySelector.searchOrAddMore')
            }
            helperText={helperText}
            required={required}
            size={size}
            error={error || (touched && required && selectedIds.length === 0)}
            inputProps={{
              ...params.inputProps,
              required: required && selectedIds.length === 0,
            }}
            onBlur={() => setTouched(true)}
          />
        )}
        sx={{
          '& .MuiAutocomplete-inputRoot': {
            minHeight: size === 'medium' ? 56 : 40,
          },
        }}
        ListboxProps={{
          style: { maxHeight: 400 },
        }}
      />

      {/* Display selected repositories */}
      {selectedRepos.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
            {allowReorder && selectedRepos.length > 1
              ? t('multiRepositorySelector.selectedCountWithOrder', { count: selectedRepos.length })
              : t('multiRepositorySelector.selectedCount', { count: selectedRepos.length })}
          </Typography>
          <Stack spacing={1}>
            {selectedRepos.map((repo, index) => (
              <Box
                key={repo.id}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  p: 1.5,
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  bgcolor: 'background.paper',
                  '&:hover': {
                    bgcolor: 'action.hover',
                  },
                }}
              >
                {allowReorder && selectedRepos.length > 1 && (
                  <Typography
                    variant="body2"
                    sx={{
                      minWidth: 24,
                      fontWeight: 600,
                      color: 'text.secondary',
                    }}
                  >
                    {index + 1}.
                  </Typography>
                )}

                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <RepoMenuItem
                    name={repo.name}
                    path={repo.path}
                    borgVersion={repo.borg_version}
                    mode={repo.mode as 'full' | 'observe' | undefined}
                    hasRunningMaintenance={repo.has_running_maintenance}
                  />
                </Box>

                <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                  {allowReorder && selectedRepos.length > 1 && (
                    <>
                      <Tooltip title={t('multiRepositorySelector.moveUp')} arrow>
                        <span>
                          <IconButton
                            size="small"
                            disabled={index === 0 || disabled}
                            onClick={() => handleMoveUp(index)}
                          >
                            <ChevronUp size={18} />
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title={t('multiRepositorySelector.moveDown')} arrow>
                        <span>
                          <IconButton
                            size="small"
                            disabled={index === selectedRepos.length - 1 || disabled}
                            onClick={() => handleMoveDown(index)}
                          >
                            <ChevronDown size={18} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </>
                  )}
                  <Tooltip title={t('multiRepositorySelector.remove')} arrow>
                    <span>
                      <IconButton
                        size="small"
                        disabled={disabled}
                        onClick={() => handleRemove(repo.id)}
                        sx={{ color: 'error.main' }}
                      >
                        <X size={18} />
                      </IconButton>
                    </span>
                  </Tooltip>
                </Box>
              </Box>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  )
}

export default MultiRepositorySelector
