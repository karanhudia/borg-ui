import React from 'react'
import { useState } from 'react'
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  Stack,
  IconButton,
  InputAdornment,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'

interface SourceDirectoriesInputProps {
  directories: string[]
  onChange: (directories: string[]) => void
  onBrowseClick?: () => void
  disabled?: boolean
  required?: boolean
}

export default function SourceDirectoriesInput({
  directories,
  onChange,
  onBrowseClick,
  disabled = false,
  required = true,
}: SourceDirectoriesInputProps) {
  const [newDir, setNewDir] = useState('')

  const handleAdd = () => {
    if (newDir.trim()) {
      onChange([...directories, newDir.trim()])
      setNewDir('')
    }
  }

  const handleRemove = (index: number) => {
    onChange(directories.filter((_, i) => i !== index))
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAdd()
    }
  }

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Source Directories & Files
        {required && (
          <Box component="span" sx={{ color: 'error.main' }}>
            {' '}
            *
          </Box>
        )}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        Specify which directories or files to backup to this repository
        {required ? ' (at least one required)' : ' (optional)'}
      </Typography>

      {required && directories.length === 0 && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          At least one source directory or file is required. Add the directories or files you want
          to backup.
        </Alert>
      )}

      {directories.length > 0 && (
        <Stack spacing={0.5} sx={{ mb: 1.5 }}>
          {directories.map((dir, index) => (
            <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                {dir}
              </Typography>
              <IconButton size="small" onClick={() => handleRemove(index)} disabled={disabled}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Box>
          ))}
        </Stack>
      )}

      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          value={newDir}
          onChange={(e) => setNewDir(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="/home/user/documents or /var/log/app.log"
          size="small"
          fullWidth
          disabled={disabled}
          InputProps={{
            endAdornment: onBrowseClick && (
              <InputAdornment position="end">
                <IconButton
                  onClick={onBrowseClick}
                  edge="end"
                  size="small"
                  title="Browse directories and files"
                  disabled={disabled}
                >
                  <FolderOpenIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
        <Button variant="outlined" size="small" onClick={handleAdd} disabled={disabled}>
          Add
        </Button>
      </Box>
    </Box>
  )
}
