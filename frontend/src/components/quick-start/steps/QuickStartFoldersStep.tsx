import { useState } from 'react'
import { Box, Button, Chip, Stack, Typography } from '@mui/material'
import { Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import PathSelectorField from '../../shared/PathSelectorField'
import type { QuickStartStepProps } from '../quickStartState'

export default function QuickStartFoldersStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState('')

  const addPaths = (paths: string[]) => {
    const next = [...answers.sourcePaths]
    for (const path of paths.map((value) => value.trim()).filter(Boolean)) {
      if (!next.includes(path)) next.push(path)
    }
    onChange({ sourcePaths: next })
    setDraft('')
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h3">
          {t('quickStart.folders.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {t('quickStart.folders.hint')}
        </Typography>
      </Box>

      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
        <PathSelectorField
          label={t('quickStart.folders.pathLabel')}
          value={draft}
          onChange={setDraft}
          placeholder="/local/home"
          multiSelect
          onSelectPaths={addPaths}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addPaths([draft])
            }
          }}
        />
        <Button
          variant="outlined"
          onClick={() => addPaths([draft])}
          disabled={!draft.trim()}
          sx={{ flexShrink: 0, height: 40 }}
        >
          {t('quickStart.folders.add')}
        </Button>
      </Stack>

      {answers.sourcePaths.length === 0 ? (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {t('quickStart.folders.empty')}
        </Typography>
      ) : (
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
          {answers.sourcePaths.map((path) => (
            <Chip
              key={path}
              icon={<Folder size={14} />}
              label={path}
              onDelete={() =>
                onChange({ sourcePaths: answers.sourcePaths.filter((item) => item !== path) })
              }
              sx={{ maxWidth: '100%', fontFamily: 'monospace' }}
            />
          ))}
        </Stack>
      )}
    </Stack>
  )
}
