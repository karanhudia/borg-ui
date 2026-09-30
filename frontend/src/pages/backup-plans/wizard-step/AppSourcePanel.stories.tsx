import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'
import { useTranslation } from 'react-i18next'

import api from '../../../services/api'
import {
  immichFound,
  immichStats,
  immichTemplate,
} from '../../../components/app-templates/appTemplates.fixtures'
import type { SourceLocation } from '../../../types'
import AppSourcePanel from './AppSourcePanel'

const immichInPlan: SourceLocation = {
  source_type: 'local',
  source_ssh_connection_id: null,
  agent_machine_id: null,
  paths: ['/local/srv/immich', '/local/srv/photos'],
  app: {
    template_id: 'immich',
    display_name: 'Immich',
    root: '/local/srv/immich',
    exclude_patterns: ['/local/srv/immich/thumbs'],
    script_execution_target: 'source',
  },
}

function Harness({ initial }: { initial: SourceLocation[] }) {
  const { t } = useTranslation()
  const [ready, setReady] = useState(false)
  const [locations, setLocations] = useState(initial)
  const [sourceKey, setSourceKey] = useState<string>('local')
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet('/source-discovery/apps').reply(200, { templates: [immichTemplate] })
    mock.onPost('/source-discovery/apps/detect').reply(200, {
      detections: [immichFound],
      warnings: [],
    })
    mock.onPost('/source-discovery/apps/inspect').reply(200, {
      root_status: 'ok',
      user: 'root',
      folders: immichStats,
      warnings: [],
    })
    setReady(true)
    return () => mock.restore()
  }, [])
  if (!ready) return null
  return (
    <Box sx={{ width: { xs: '100%', sm: 720 }, p: 2 }}>
      <AppSourcePanel
        sshConnections={[]}
        sourceKey={sourceKey}
        onSourceKeyChange={setSourceKey}
        appLocations={locations}
        onAdd={(location) => setLocations((current) => [...current, location])}
        onRemove={(location) =>
          setLocations((current) => current.filter((item) => item !== location))
        }
        machineLabel={() => t('backupPlans.sourceChooser.borgUiServer')}
        t={t}
      />
    </Box>
  )
}

const meta = {
  title: 'Backup Plans/AppSourcePanel',
  component: Harness,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof Harness>

export default meta
type Story = StoryObj<typeof meta>

export const Empty: Story = { args: { initial: [] } }

export const WithAppInPlan: Story = { args: { initial: [immichInPlan] } }
