import React from 'react'
import { Autocomplete, TextField, Box, Typography, Stack, IconButton, Tooltip } from '@mui/material'
import { HardDrive, ChevronUp, ChevronDown, X } from 'lucide-react'

export interface Repository {
  id: number
  name: string
  path: string
}

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
  showValidation?: boolean // Only show error if explicitly requested (e.g., after submit attempt)
  filterMode?: 'observe' | null // Exclude repositories with this mode
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
  showValidation = false,
  filterMode = null,
}) => {
  // Ensure repositories is always an array
  const safeRepositories = Array.isArray(repositories) ? repositories : []

  // Filter repositories if needed
  const availableRepos = filterMode
    ? safeRepositories.filter((repo: any) => repo.mode !== filterMode)
    : safeRepositories

  // Get selected repositories in order
  const selectedRepos = selectedIds
    .map((id) => availableRepos.find((r) => r.id === id))
    .filter(Boolean) as Repository[]

  // Debug logging (temporary)
  if (process.env.NODE_ENV === 'development' && selectedIds.length > 0) {
    console.log('[MultiRepositorySelector] selectedIds:', selectedIds)
    console.log('[MultiRepositorySelector] selectedRepos:', selectedRepos.map(r => ({ id: r.id, name: r.name })))
  }

  // Handle reordering
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
        onChange={(_, newValue) => {
          // Use the order from the autocomplete selection
          const newIds = newValue.map((r) => r.id)
          // Remove duplicates (in case of any bug) and preserve selection order
          const uniqueIds = Array.from(new Set(newIds))
          onChange(uniqueIds)
        }}
        getOptionLabel={(option) => option.name}
        isOptionEqualToValue={(option, value) => option.id === value.id}
        renderOption={(props, option) => (
          <Box component="li" {...props}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 0.5, width: '100%' }}>
              <HardDrive size={16} style={{ flexShrink: 0 }} />
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {option.name}
                </Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    display: 'block',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {option.path}
                </Typography>
              </Box>
            </Stack>
          </Box>
        )}
        renderTags={() => null} // We render tags manually below
        renderInput={(params) => (
          <TextField
            {...params}
            label={label}
            placeholder={selectedIds.length === 0 ? placeholder : 'Search or add more...'}
            helperText={helperText}
            required={required}
            size={size}
            error={error || (showValidation && required && selectedIds.length === 0)}
            inputProps={{
              ...params.inputProps,
              required: required && selectedIds.length === 0,
            }}
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
              ? `Selected repositories (${selectedRepos.length}) - Use arrows to change backup order`
              : `Selected repositories (${selectedRepos.length})`}
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

                <HardDrive
                  size={16}
                  style={{ flexShrink: 0, color: 'var(--mui-palette-text-secondary)' }}
                />

                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Typography variant="body2" fontWeight={500}>
                    {repo.name}
                  </Typography>
                  <Tooltip title={repo.path} placement="top">
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.7rem',
                        display: 'block',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {repo.path}
                    </Typography>
                  </Tooltip>
                </Box>

                <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                  {allowReorder && selectedRepos.length > 1 && (
                    <>
                      <Tooltip title="Move up" arrow>
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
                      <Tooltip title="Move down" arrow>
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
                  <Tooltip title="Remove" arrow>
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
