import { useEffect, useState } from 'react'
import { Box, TextField } from '@mui/material'
import { useTranslation } from 'react-i18next'
import RichSelect from '../shared/RichSelect'
import type { IndexMode } from '../../types/operations'

const MODES: IndexMode[] = ['full', 'archives', 'off']

// One glob pattern per line, blank lines and stray whitespace dropped.
function parsePatterns(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

export interface IndexModeSettingsProps {
  mode: IndexMode
  excludes: string[]
  onModeChange: (mode: IndexMode) => void
  onExcludesChange: (excludes: string[]) => void
}

// How much derived data this repository keeps refreshed (spec 6.8), and the
// glob patterns the file history index drops from borg diff output (6.7).
// The two sit together because the excludes trim what an index records and
// the mode says whether it records at all. State and saving belong to the
// wizard, as they do for every other field on its Advanced step.
export default function IndexModeSettings({
  mode,
  excludes,
  onModeChange,
  onExcludesChange,
}: IndexModeSettingsProps) {
  const { t } = useTranslation()
  const indexesHistory = mode === 'full'
  // The raw text is held here and the parsed patterns are reported up, so
  // typing a blank line or a leading space is not rewritten under the
  // cursor. Reseeded only when the patterns actually change from outside,
  // which is the dialog opening on another repository.
  const [text, setText] = useState(() => excludes.join('\n'))
  useEffect(() => {
    const incoming = excludes.join('\n')
    setText((current) => (parsePatterns(current).join('\n') === incoming ? current : incoming))
  }, [excludes])

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <RichSelect
        label={t('repositoryIndexMode.label')}
        value={mode}
        onChange={(value) => onModeChange(value as IndexMode)}
        options={MODES.map((value) => ({
          value,
          primary: t(`repositoryIndexMode.mode.${value}.title`),
          secondary: t(`repositoryIndexMode.mode.${value}.cost`),
        }))}
      />
      <TextField
        label={t('repositoryIndexMode.excludes')}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          onExcludesChange(parsePatterns(event.target.value))
        }}
        multiline
        minRows={3}
        fullWidth
        disabled={!indexesHistory}
        // Kept on screen rather than hidden when it does not apply, so the
        // patterns someone typed are not silently discarded and the reason
        // they are inactive is visible.
        helperText={t(
          indexesHistory
            ? 'repositoryIndexMode.excludesHelp'
            : 'repositoryIndexMode.excludesInactive'
        )}
      />
    </Box>
  )
}
