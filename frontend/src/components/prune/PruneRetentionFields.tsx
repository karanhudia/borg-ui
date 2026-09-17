import { useTranslation } from 'react-i18next'
import { Box, Typography, InputBase, alpha, useTheme } from '@mui/material'
import { Clock, Sun, CalendarDays, CalendarRange, Calendar } from 'lucide-react'
import type { PruneRetention } from '../../types/archives'

export interface PruneRetentionFieldsProps {
  value: PruneRetention
  onChange: (next: PruneRetention) => void
  disabled?: boolean
}

export default function PruneRetentionFields({
  value,
  onChange,
  disabled,
}: PruneRetentionFieldsProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const borderColor = isDark ? alpha('#fff', 0.08) : alpha('#000', 0.09)

  const retentionFields = [
    {
      key: 'keep_hourly' as const,
      icon: <Clock size={14} />,
      label: t('dialogs.prune.keepHourly'),
    },
    {
      key: 'keep_daily' as const,
      icon: <Sun size={14} />,
      label: t('dialogs.prune.keepDaily'),
    },
    {
      key: 'keep_weekly' as const,
      icon: <CalendarDays size={14} />,
      label: t('dialogs.prune.keepWeekly'),
    },
    {
      key: 'keep_monthly' as const,
      icon: <CalendarRange size={14} />,
      label: t('dialogs.prune.keepMonthly'),
    },
    {
      key: 'keep_quarterly' as const,
      icon: <CalendarRange size={14} />,
      label: t('dialogs.prune.keepQuarterly'),
    },
    {
      key: 'keep_yearly' as const,
      icon: <Calendar size={14} />,
      label: t('dialogs.prune.keepYearly'),
    },
  ]

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor,
        borderRadius: 1.5,
        overflow: 'hidden',
        mb: 0.75,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          px: 1.75,
          py: 0.9,
          borderBottom: '1px solid',
          borderColor,
          bgcolor: isDark ? alpha('#fff', 0.015) : alpha('#000', 0.012),
          '&:hover': {
            bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.025),
          },
          transition: 'background-color 150ms',
        }}
      >
        <Box sx={{ color: 'text.disabled', display: 'flex', flexShrink: 0 }}>
          <Clock size={14} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" sx={{ fontSize: '0.8rem' }}>
            {t('dialogs.prune.keepWithin')}
          </Typography>
          <Typography
            variant="caption"
            sx={{
              color: 'text.disabled',
            }}
          >
            {t('dialogs.prune.keepWithinHelper')}
          </Typography>
        </Box>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            border: '1px solid',
            borderColor,
            borderRadius: 1,
            px: 1,
            py: 0.35,
            bgcolor: 'background.paper',
            width: 96,
          }}
        >
          <InputBase
            value={value.keep_within}
            onChange={(e) => onChange({ ...value, keep_within: e.target.value })}
            disabled={disabled}
            inputProps={{
              'aria-label': t('dialogs.prune.keepWithin'),
              style: { textAlign: 'center', padding: 0 },
            }}
            placeholder={t('dialogs.prune.keepWithinPlaceholder')}
            sx={{
              fontSize: '0.85rem',
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
              flex: 1,
            }}
          />
        </Box>
      </Box>
      {retentionFields.map((field, i) => (
        <Box
          key={field.key}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            px: 1.75,
            py: 0.9,
            borderBottom: i < retentionFields.length - 1 ? '1px solid' : 0,
            borderColor,
            bgcolor: isDark ? alpha('#fff', 0.015) : alpha('#000', 0.012),
            '&:hover': {
              bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.025),
            },
            transition: 'background-color 150ms',
          }}
        >
          <Box sx={{ color: 'text.disabled', display: 'flex', flexShrink: 0 }}>{field.icon}</Box>
          <Typography variant="body2" sx={{ flex: 1, fontSize: '0.8rem' }}>
            {field.label}
          </Typography>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              border: '1px solid',
              borderColor,
              borderRadius: 1,
              px: 1,
              py: 0.35,
              bgcolor: 'background.paper',
              width: 72,
            }}
          >
            <InputBase
              type="number"
              value={value[field.key]}
              onChange={(e) =>
                onChange({ ...value, [field.key]: Math.max(0, parseInt(e.target.value, 10) || 0) })
              }
              disabled={disabled}
              inputProps={{
                min: 0,
                'aria-label': field.label,
                style: { textAlign: 'center', padding: 0 },
              }}
              sx={{
                fontSize: '0.85rem',
                fontWeight: 600,
                fontVariantNumeric: 'tabular-nums',
                flex: 1,
              }}
            />
          </Box>
        </Box>
      ))}
    </Box>
  )
}
