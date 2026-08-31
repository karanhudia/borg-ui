import {
  FormControl,
  FormControlLabel,
  FormLabel,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { BorgInstallMode } from './agentInstallCommandText'

const borgInstallOptions: BorgInstallMode[] = ['borg1', 'borg2', 'both', 'skip']

// The Borg selection cards shared by the add-agent wizard and the reinstall
// dialog. The two contexts describe the same choices differently (install vs
// verify/update, and which option is the default), so the labels come from the
// caller's i18n prefix: `${i18nPrefix}.borgInstallation` for the legend and
// `${i18nPrefix}.borgOptions.<option>.{label,description}` for the cards.
export default function BorgInstallModeRadioGroup({
  value,
  onChange,
  i18nPrefix,
}: {
  value: BorgInstallMode
  onChange: (mode: BorgInstallMode) => void
  i18nPrefix: string
}) {
  const { t } = useTranslation()

  return (
    <FormControl component="fieldset">
      <FormLabel component="legend">{t(`${i18nPrefix}.borgInstallation`)}</FormLabel>
      <RadioGroup
        value={value}
        onChange={(event) => onChange(event.target.value as BorgInstallMode)}
        sx={{
          mt: 1,
          display: 'grid',
          gap: 1,
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
        }}
      >
        {borgInstallOptions.map((option) => {
          const selected = value === option
          return (
            <FormControlLabel
              key={option}
              value={option}
              control={<Radio />}
              label={
                <Stack spacing={0.35} sx={{ minWidth: 0 }}>
                  <Typography
                    sx={{
                      fontWeight: 700,
                    }}
                  >
                    {t(`${i18nPrefix}.borgOptions.${option}.label`)}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: 'text.secondary',
                    }}
                  >
                    {t(`${i18nPrefix}.borgOptions.${option}.description`)}
                  </Typography>
                </Stack>
              }
              sx={{
                m: 0,
                p: 1.25,
                alignItems: 'flex-start',
                border: '1px solid',
                borderColor: selected ? 'primary.main' : 'divider',
                borderRadius: 1,
                bgcolor: selected ? 'action.hover' : 'background.paper',
                cursor: 'pointer',
                transition: 'border-color 180ms ease, background-color 180ms ease',
                '&:hover': {
                  borderColor: selected ? 'primary.main' : 'text.secondary',
                  bgcolor: 'action.hover',
                },
                '& .MuiFormControlLabel-label': { width: '100%' },
              }}
            />
          )
        })}
      </RadioGroup>
    </FormControl>
  )
}
