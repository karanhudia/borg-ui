import { Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { useT } from './tokens'

function LegendItem({ count, color, label }: { count: number; color: string; label: string }) {
  const T = useT()
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: 'baseline' }}>
      <Typography
        sx={{ fontFamily: T.mono, fontWeight: 700, color, fontSize: '0.875rem', lineHeight: 1 }}
      >
        {count}
      </Typography>
      <Typography sx={{ fontSize: '0.75rem', color: T.textMuted }}>{label}</Typography>
    </Stack>
  )
}

// The rail is 200px wide, so longer translations (German "fehlgeschlagen")
// wrap the second item onto its own line instead of overflowing the card.
export function SuccessDonutLegend({ passed, failed }: { passed: number; failed: number }) {
  const { t } = useTranslation()
  const T = useT()
  return (
    <Stack
      direction="row"
      useFlexGap
      sx={{ flexWrap: 'wrap', justifyContent: 'space-between', columnGap: 1.5, rowGap: 0.75 }}
    >
      <LegendItem count={passed} color={T.green} label={t('dashboard.successDonut.passed')} />
      <LegendItem
        count={failed}
        color={failed > 0 ? T.red : T.textMuted}
        label={t('dashboard.successDonut.failed')}
      />
    </Stack>
  )
}
