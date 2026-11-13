import type { TFunction } from 'i18next'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { useState } from 'react'
import { fn } from 'storybook/test'
import i18n from '../../../i18n'
import { SystemKeyCard } from './SystemKeyCard'

const t = i18n.t.bind(i18n) as TFunction

function SystemKeyCardStory({ keyExists }: { keyExists: boolean }) {
  const theme = useTheme()
  const [keyVisible, setKeyVisible] = useState(false)
  const [fingerprintVisible, setFingerprintVisible] = useState(false)
  return (
    <Box sx={{ p: 3, maxWidth: 900, bgcolor: 'background.default' }}>
      <SystemKeyCard
        t={t}
        theme={theme}
        isDark={theme.palette.mode === 'dark'}
        keyExists={keyExists}
        systemKey={
          keyExists
            ? {
                id: 1,
                key_type: 'ed25519',
                fingerprint: 'SHA256:Zx9Q3n1sKk2Yy8bV0pRfT4uJ6mE7cD1aS5gH2wN0qLk',
                public_key: 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample borg-ui',
              }
            : undefined
        }
        keyVisible={keyVisible}
        setKeyVisible={setKeyVisible}
        fingerprintVisible={fingerprintVisible}
        setFingerprintVisible={setFingerprintVisible}
        setGenerateDialogOpen={fn()}
        setImportDialogOpen={fn()}
        setDeleteKeyDialogOpen={fn()}
        onCopyPublicKey={fn()}
      />
    </Box>
  )
}

const meta = {
  title: 'Remote Machines/SystemKeyCard',
  component: SystemKeyCardStory,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof SystemKeyCardStory>

export default meta

type Story = StoryObj<typeof meta>

/** Only actions on the key itself; adding machines lives in the page header. */
export const WithKey: Story = { args: { keyExists: true } }

export const NoKey: Story = { args: { keyExists: false } }
