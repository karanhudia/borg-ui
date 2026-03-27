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
import { useTranslation } from 'react-i18next'
import { buildCompressionString, parseCompressionString } from '../utils/compressionUtils'

interface CompressionSettingsProps {
  value: string // The full compression string (e.g., "auto,lz4,6")
  onChange: (compressionString: string) => void
  disabled?: boolean
}

// Valid borg obfuscation levels:
//   1-6: relative random reciprocal (small overhead)
//   110-123: random additive padding (up to 8MB)
//   250: Padmé deterministic padding (≤12% overhead, added in borg 1.4.1)
const isValidObfuscateLevel = (val: string): boolean => {
  if (val === '') return true
  const n = parseInt(val, 10)
  if (isNaN(n) || String(n) !== val) return false
  return (n >= 1 && n <= 6) || (n >= 110 && n <= 123) || n === 250
}

export default function CompressionSettings({
  value,
  onChange,
  disabled = false,
}: CompressionSettingsProps) {
  const { t } = useTranslation()
  const parsed = parseCompressionString(value || 'lz4')
  const [algorithm, setAlgorithm] = useState(parsed.algorithm)
  const [level, setLevel] = useState(parsed.level)
  const [autoDetect, setAutoDetect] = useState(parsed.autoDetect)
  const [obfuscate, setObfuscate] = useState(parsed.obfuscate)
  const obfuscateError = !isValidObfuscateLevel(obfuscate)

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
        {t('compressionSettings.title')}
      </Typography>

      <Stack spacing={2}>
        <FormControl fullWidth disabled={disabled}>
          <InputLabel>{t('compressionSettings.algorithmLabel')}</InputLabel>
          <Select
            value={algorithm}
            label={t('compressionSettings.algorithmLabel')}
            onChange={(e) => setAlgorithm(e.target.value)}
          >
            <MenuItem value="none">{t('compressionSettings.algorithmNone')}</MenuItem>
            <MenuItem value="lz4">{t('compressionSettings.algorithmLz4')}</MenuItem>
            <MenuItem value="zstd">{t('compressionSettings.algorithmZstd')}</MenuItem>
            <MenuItem value="zlib">{t('compressionSettings.algorithmZlib')}</MenuItem>
            <MenuItem value="lzma">{t('compressionSettings.algorithmLzma')}</MenuItem>
            <MenuItem value="auto">{t('compressionSettings.algorithmAuto')}</MenuItem>
          </Select>
        </FormControl>

        {algorithm !== 'none' && (
          <>
            <TextField
              label={t('compressionSettings.levelLabel')}
              type="number"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              placeholder={
                algorithm === 'zstd'
                  ? t('compressionSettings.levelPlaceholderZstd')
                  : algorithm === 'zlib'
                    ? t('compressionSettings.levelPlaceholderZlib')
                    : algorithm === 'lzma'
                      ? t('compressionSettings.levelPlaceholderLzma')
                      : t('compressionSettings.levelPlaceholderDefault')
              }
              helperText={
                algorithm === 'auto'
                  ? t('compressionSettings.levelHelperAuto')
                  : algorithm === 'zstd'
                    ? t('compressionSettings.levelHelperZstd')
                    : algorithm === 'zlib'
                      ? t('compressionSettings.levelHelperZlib')
                      : algorithm === 'lzma'
                        ? t('compressionSettings.levelHelperLzma')
                        : t('compressionSettings.levelHelperDefault')
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
                  label={t('compressionSettings.autoDetect')}
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: -1, mb: 1, display: 'block' }}
                >
                  {t('compressionSettings.autoDetectDesc')}
                </Typography>
              </>
            )}

            <TextField
              label={t('compressionSettings.obfuscateLabel')}
              type="number"
              value={obfuscate}
              onChange={(e) => setObfuscate(e.target.value)}
              placeholder={t('compressionSettings.obfuscatePlaceholder')}
              helperText={
                obfuscateError
                  ? t('compressionSettings.obfuscateErrorInvalid')
                  : t('compressionSettings.obfuscateHelper')
              }
              error={obfuscateError}
              fullWidth
              disabled={disabled}
            />

            <Alert severity="info" sx={{ mt: 1 }}>
              {t('compressionSettings.finalSpec')}{' '}
              <strong>{buildCompressionString(algorithm, level, autoDetect, obfuscate)}</strong>
            </Alert>
          </>
        )}
      </Stack>
    </Box>
  )
}
