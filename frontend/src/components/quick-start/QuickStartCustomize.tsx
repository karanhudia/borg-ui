import { useCallback } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  FormControlLabel,
  Stack,
  Switch,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import CompressionSettings from '../CompressionSettings'
import PruneSettingsInput from '../PruneSettingsInput'
import { getDefaultRepositoryEncryption } from '../wizard/repositoryEncryption'
import type {
  QuickStartAnswers,
  QuickStartSettings,
  QuickStartSettingsChange,
} from './quickStartState'

interface QuickStartCustomizeProps {
  answers: QuickStartAnswers
  onSettingsChange: QuickStartSettingsChange
  canUseBorg2: boolean
}

export default function QuickStartCustomize({
  answers,
  onSettingsChange: update,
  canUseBorg2,
}: QuickStartCustomizeProps) {
  const { t } = useTranslation()
  const { settings } = answers
  const encrypted = settings.encryption !== 'none'
  const setCompression = useCallback((compression: string) => update({ compression }), [update])

  const toggle = (key: keyof QuickStartSettings, label: string, hint: string) => (
    <FormControlLabel
      control={
        <Switch
          checked={Boolean(settings[key])}
          onChange={(event) => update({ [key]: event.target.checked })}
        />
      }
      label={
        <span>
          <Typography variant="body2" component="span" sx={{ display: 'block' }}>
            {label}
          </Typography>
          <Typography variant="caption" component="span" sx={{ color: 'text.secondary' }}>
            {hint}
          </Typography>
        </span>
      }
      sx={{ alignItems: 'flex-start', '& .MuiSwitch-root': { mt: -0.5 } }}
    />
  )

  return (
    <Accordion
      disableGutters
      variant="outlined"
      sx={{ borderRadius: 2, '&:before': { display: 'none' } }}
    >
      <AccordionSummary expandIcon={<ChevronDown size={18} />}>
        <Stack>
          <Typography variant="subtitle2">{t('quickStart.customize.title')}</Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {t('quickStart.customize.subtitle')}
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2.5}>
          {toggle(
            'scheduleEnabled',
            t('quickStart.customize.schedule'),
            t('quickStart.customize.scheduleHint')
          )}
          <FormControlLabel
            control={
              <Switch
                checked={encrypted}
                onChange={(event) =>
                  update({
                    encryption: event.target.checked
                      ? getDefaultRepositoryEncryption(settings.borgVersion)
                      : 'none',
                  })
                }
              />
            }
            label={
              <span>
                <Typography variant="body2" component="span" sx={{ display: 'block' }}>
                  {t('quickStart.customize.encrypt')}
                </Typography>
                <Typography variant="caption" component="span" sx={{ color: 'text.secondary' }}>
                  {t('quickStart.customize.encryptHint')}
                </Typography>
              </span>
            }
            sx={{ alignItems: 'flex-start', '& .MuiSwitch-root': { mt: -0.5 } }}
          />
          {toggle(
            'runPruneAfter',
            t('quickStart.customize.prune'),
            t('quickStart.customize.pruneHint')
          )}
          {settings.runPruneAfter && (
            <PruneSettingsInput values={settings.prune} onChange={(prune) => update({ prune })} />
          )}
          {toggle(
            'runCompactAfter',
            t('quickStart.customize.compact'),
            t('quickStart.customize.compactHint')
          )}
          {toggle(
            'runCheckAfter',
            t('quickStart.customize.check'),
            t('quickStart.customize.checkHint')
          )}

          <CompressionSettings value={settings.compression} onChange={setCompression} />

          {canUseBorg2 && (
            <Stack spacing={1}>
              <Typography variant="subtitle2">{t('quickStart.customize.borgVersion')}</Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={settings.borgVersion}
                onChange={(_event, value: 1 | 2 | null) => {
                  if (!value) return
                  update({
                    borgVersion: value,
                    encryption: encrypted ? getDefaultRepositoryEncryption(value) : 'none',
                  })
                }}
              >
                <ToggleButton value={1}>Borg 1</ToggleButton>
                <ToggleButton value={2}>Borg 2</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  )
}
