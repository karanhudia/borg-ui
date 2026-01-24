import { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Checkbox,
  FormControlLabel,
  Alert,
  Stack,
} from '@mui/material'
import { buildCompressionString, parseCompressionString } from '../utils/compressionUtils'

interface CompressionSettingsProps {
  value: string // The full compression string (e.g., "auto,lz4,6")
  onChange: (compressionString: string) => void
  disabled?: boolean
}

export default function CompressionSettings({
  value,
  onChange,
  disabled = false,
}: CompressionSettingsProps) {
  const parsed = parseCompressionString(value || 'lz4')
  const [algorithm, setAlgorithm] = useState(parsed.algorithm)
  const [level, setLevel] = useState(parsed.level)
  const [autoDetect, setAutoDetect] = useState(parsed.autoDetect)
  const [obfuscate, setObfuscate] = useState(parsed.obfuscate)

  // Update parent when any value changes
  useEffect(() => {
    const newCompression = buildCompressionString(algorithm, level, autoDetect, obfuscate)
    onChange(newCompression)
  }, [algorithm, level, autoDetect, obfuscate, onChange])

  // Sync with external changes
  useEffect(() => {
    const parsed = parseCompressionString(value || 'lz4')
    setAlgorithm(parsed.algorithm)
    setLevel(parsed.level)
    setAutoDetect(parsed.autoDetect)
    setObfuscate(parsed.obfuscate)
  }, [value])

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom sx={{ mb: 1.5 }}>
        Compression Settings
      </Typography>

      <Stack spacing={2}>
        <FormControl fullWidth disabled={disabled}>
          <InputLabel>Compression Algorithm</InputLabel>
          <Select
            value={algorithm}
            label="Compression Algorithm"
            onChange={(e) => setAlgorithm(e.target.value)}
          >
            <MenuItem value="none">none - Do not compress</MenuItem>
            <MenuItem value="lz4">lz4 - Very high speed, very low compression (default)</MenuItem>
            <MenuItem value="zstd">zstd - Modern wide-range algorithm (default level 3)</MenuItem>
            <MenuItem value="zlib">
              zlib - Medium speed, medium compression (default level 6)
            </MenuItem>
            <MenuItem value="lzma">lzma - Low speed, high compression (default level 6)</MenuItem>
            <MenuItem value="auto">auto - Automatic compression selection</MenuItem>
            <MenuItem value="obfuscate">obfuscate - Obfuscate compressed data</MenuItem>
          </Select>
        </FormControl>

        {algorithm !== 'none' && (
          <>
            <TextField
              label="Compression Level (Optional)"
              type="number"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              placeholder={
                algorithm === 'zstd'
                  ? '1-22 (default: 3)'
                  : algorithm === 'zlib'
                    ? '0-9 (default: 6)'
                    : algorithm === 'lzma'
                      ? '0-9 (default: 6, max useful: 6)'
                      : 'Leave empty for default'
              }
              helperText={
                algorithm === 'auto'
                  ? 'Auto algorithm uses lz4 as fallback. Level setting not applicable.'
                  : algorithm === 'zstd'
                    ? 'zstd: Level 1-22. Higher = better compression but slower.'
                    : algorithm === 'zlib'
                      ? 'zlib: Level 0-9. Level 0 means no compression (use "none" instead).'
                      : algorithm === 'lzma'
                        ? 'lzma: Level 0-9. Levels above 6 are pointless and waste CPU/RAM.'
                        : 'Leave empty to use default level.'
              }
              fullWidth
              disabled={disabled || algorithm === 'auto'}
            />

            {algorithm !== 'auto' && algorithm !== 'obfuscate' && (
              <>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={autoDetect}
                      onChange={(e) => setAutoDetect(e.target.checked)}
                      disabled={disabled}
                    />
                  }
                  label="Auto-detect compressibility (auto,C[,L])"
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: -1, mb: 1, display: 'block' }}
                >
                  Uses lz4 to test if data is compressible. For incompressible data (e.g., media
                  files), uses "none". For compressible data, uses your selected algorithm.
                </Typography>
              </>
            )}

            <TextField
              label="Obfuscate Spec (Optional)"
              type="number"
              value={obfuscate}
              onChange={(e) => setObfuscate(e.target.value)}
              placeholder="e.g., 110, 250"
              helperText="Obfuscate compressed chunk sizes to make fingerprinting attacks harder. Must be used with encryption. Repo will be bigger."
              fullWidth
              disabled={disabled}
            />

            <Alert severity="info" sx={{ mt: 1 }}>
              Final compression spec:{' '}
              <strong>{buildCompressionString(algorithm, level, autoDetect, obfuscate)}</strong>
            </Alert>
          </>
        )}
      </Stack>
    </Box>
  )
}
