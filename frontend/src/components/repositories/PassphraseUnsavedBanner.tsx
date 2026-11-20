import { Alert, AlertTitle, Box, Button, Typography } from '@mui/material'
import { KeyRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface FlaggedRepository {
  id: number
  name: string
  passphrase_unsaved?: boolean
}

interface PassphraseUnsavedBannerProps {
  repositories: FlaggedRepository[]
  onReveal: (repositoryId: number) => void
}

/** Repositories whose generated passphrase nobody saved yet (MCP spec 5.9). */
export default function PassphraseUnsavedBanner({
  repositories,
  onReveal,
}: PassphraseUnsavedBannerProps) {
  const { t } = useTranslation()
  const flagged = repositories.filter((repo) => repo.passphrase_unsaved)
  if (flagged.length === 0) return null

  return (
    <Alert
      severity="warning"
      icon={<KeyRound size={20} />}
      sx={{
        border: '1px solid',
        borderColor: 'warning.main',
        mb: 2,
        '& .MuiAlert-message': { flex: 1, minWidth: 0 },
      }}
    >
      <AlertTitle>
        {t('repositories.passphraseUnsaved.title', { count: flagged.length })}
      </AlertTitle>
      <Typography variant="body2" sx={{ mb: 1.5 }}>
        {t('repositories.passphraseUnsaved.why')}
      </Typography>
      <Box
        component="ul"
        sx={{
          m: 0,
          p: 0,
          listStyle: 'none',
          maxWidth: 560,
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) auto',
          columnGap: 2,
          rowGap: 1,
          alignItems: 'center',
        }}
      >
        {flagged.map((repo) => (
          <Box component="li" key={repo.id} sx={{ display: 'contents' }}>
            <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
              {repo.name}
            </Typography>
            <Button
              size="small"
              variant="outlined"
              color="warning"
              onClick={() => onReveal(repo.id)}
              aria-label={t('repositories.passphraseUnsaved.revealFor', { name: repo.name })}
              sx={{ minHeight: 36 }}
            >
              {t('repositories.passphraseUnsaved.reveal')}
            </Button>
          </Box>
        ))}
      </Box>
    </Alert>
  )
}
