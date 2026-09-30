import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { useTranslation } from 'react-i18next'

import api from '../../../services/api'
import {
  immichFound,
  immichStats,
  immichTemplate,
} from '../../../components/app-templates/appTemplates.fixtures'
import { createInitialState } from '../state'
import { AppTemplateDialog } from './AppTemplateDialog'

function DialogHarness({ readable }: { readable: boolean }) {
  const { t } = useTranslation()
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet('/source-discovery/apps').reply(200, { templates: [immichTemplate] })
    mock.onPost('/source-discovery/apps/inspect').reply(200, { folders: immichStats, warnings: [] })
    mock.onPost('/source-discovery/apps/detect').reply(200, {
      detections: [readable ? immichFound : { ...immichFound, path: '/srv/immich', readable }],
      warnings: [],
    })
    setReady(true)
    return () => mock.restore()
  }, [readable])
  if (!ready) return null
  return (
    <AppTemplateDialog
      open
      onClose={() => {}}
      wizardState={createInitialState()}
      sshConnections={[]}
      updateState={() => {}}
      onCreateScript={async () => ({ id: 1 })}
      t={t}
    />
  )
}

const meta = {
  title: 'Backup Plans/AppTemplateDialog',
  component: DialogHarness,
} satisfies Meta<typeof DialogHarness>

export default meta
type Story = StoryObj<typeof meta>

export const ImmichFound: Story = { args: { readable: true } }

export const ImmichNotReadable: Story = { args: { readable: false } }
