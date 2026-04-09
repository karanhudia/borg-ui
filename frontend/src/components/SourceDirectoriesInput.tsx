import React from 'react'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import {
  Box,
  Typography,
  TextField,
  Button,
  Stack,
  IconButton,
  InputAdornment,
  Tooltip,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'

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
  const { t } = useTranslation()
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
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5 }}>
        <Typography variant="subtitle2">
          {t('sourceDirectories.title')}
          {required && (
            <Box component="span" sx={{ color: 'error.main' }}>
              {' '}
              *
            </Box>
          )}
        </Typography>
        {required && (
          <Tooltip title={t('sourceDirectories.warning')} arrow placement="right">
            <IconButton
              size="small"
              aria-label={t('sourceDirectories.titleHelp')}
              sx={{ p: 0.25, color: 'text.secondary' }}
            >
              <InfoOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        {t('sourceDirectories.subtitle')}
        {required
          ? t('sourceDirectories.atLeastOneRequired')
          : t('sourceDirectories.optionalSuffix')}
      </Typography>

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
          placeholder={t('sourceDirectories.placeholder')}
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
                  title={t('sourceDirectories.browseTitle')}
                  disabled={disabled}
                >
                  <FolderOpenIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
        <Button variant="outlined" size="small" onClick={handleAdd} disabled={disabled}>
          {t('sourceDirectories.add')}
        </Button>
      </Box>
    </Box>
  )
}
