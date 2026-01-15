import { useState } from 'react'
import {
  Box,
  Typography,
  TextField,
  Button,
  Stack,
  IconButton,
  InputAdornment,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'

interface ExcludePatternInputProps {
  patterns: string[]
  onChange: (patterns: string[]) => void
  onBrowseClick?: () => void
  disabled?: boolean
}

export default function ExcludePatternInput({
  patterns,
  onChange,
  onBrowseClick,
  disabled = false,
}: ExcludePatternInputProps) {
  const [newPattern, setNewPattern] = useState('')

  const handleAdd = () => {
    if (newPattern.trim()) {
      onChange([...patterns, newPattern.trim()])
      setNewPattern('')
    }
  }

  const handleRemove = (index: number) => {
    onChange(patterns.filter((_, i) => i !== index))
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
        Exclude Patterns (Optional)
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        Specify patterns to exclude from backup (e.g., *.log, *.tmp, __pycache__, node_modules)
      </Typography>

      {patterns.length > 0 && (
        <Stack spacing={0.5} sx={{ mb: 1.5 }}>
          {patterns.map((pattern, index) => (
            <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                {pattern}
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
          value={newPattern}
          onChange={(e) => setNewPattern(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="*.log or /path/to/exclude"
          size="small"
          fullWidth
          disabled={disabled}
          InputProps={{
            endAdornment: onBrowseClick && (
              <InputAdornment position="end">
                <IconButton onClick={onBrowseClick} edge="end" size="small" title="Browse to exclude" disabled={disabled}>
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
