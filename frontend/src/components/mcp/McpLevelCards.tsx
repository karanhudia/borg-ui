import { Box, Chip, FormControlLabel, Radio, RadioGroup, Typography, alpha } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { McpLevel } from '../../services/api'
import { MCP_LEVELS, levelRank } from './levels'

interface McpLevelCardsProps {
  value: McpLevel
  onChange: (level: McpLevel) => void
  /** Levels this version has tools for. */
  available: McpLevel[]
  /** The administrator's cap. */
  cap: McpLevel
}

/** The four access levels as rich radio cards, one line each. */
export default function McpLevelCards({ value, onChange, available, cap }: McpLevelCardsProps) {
  const { t } = useTranslation()
  return (
    <RadioGroup
      aria-label={t('mcp.levels.groupLabel')}
      value={value}
      onChange={(_, next) => onChange(next as McpLevel)}
      sx={{ gap: 1 }}
    >
      {MCP_LEVELS.map((level) => {
        const missing = !available.includes(level)
        const capped = !missing && levelRank(level) > levelRank(cap)
        const disabled = missing || capped
        const selected = value === level
        return (
          <FormControlLabel
            key={level}
            value={level}
            disabled={disabled}
            control={<Radio size="small" sx={{ mt: -0.25 }} />}
            sx={(theme) => ({
              m: 0,
              alignItems: 'flex-start',
              px: 1.5,
              py: 1.25,
              border: '1px solid',
              borderRadius: 2,
              borderColor: selected ? 'primary.main' : 'divider',
              bgcolor: selected ? alpha(theme.palette.primary.main, 0.06) : 'transparent',
              transition: 'border-color 150ms, background-color 150ms',
              '& .MuiFormControlLabel-label': { flex: 1, minWidth: 0 },
            })}
            label={
              <Box sx={{ pt: 0.75 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {t(`mcp.levels.${level}.title`)}
                  </Typography>
                  {disabled && (
                    <Chip
                      size="small"
                      variant="outlined"
                      label={missing ? t('mcp.levels.comingSoon') : t('mcp.levels.aboveCap')}
                    />
                  )}
                </Box>
                <Typography variant="body2" color="text.secondary">
                  {t(`mcp.levels.${level}.body`)}
                </Typography>
              </Box>
            }
          />
        )
      })}
    </RadioGroup>
  )
}
