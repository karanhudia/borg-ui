import type { TFunction } from 'i18next'
import { Box, Button, Tooltip, Typography } from '@mui/material'
import { Info, Plus, Wifi } from 'lucide-react'
import PageHeader from '../../../components/PageHeader'

interface SSHPageHeaderProps {
  t: TFunction
  /** Hidden until a system key exists: there is nothing to deploy before that. */
  showActions?: boolean
  onDeploy?: () => void
  onAddManual?: () => void
}

export function SSHPageHeader({ t, showActions, onDeploy, onAddManual }: SSHPageHeaderProps) {
  return (
    <PageHeader
      title={
        <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
          {t('sshConnections.title')}
          <Tooltip
            title={
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                  {t('sshConnections.singleKeySystem.title')}
                </Typography>
                <Typography variant="body2">
                  {t('sshConnections.singleKeySystem.description')}
                </Typography>
              </Box>
            }
            arrow
          >
            <Info
              size={16}
              style={{ color: 'inherit', opacity: 0.45, cursor: 'help', flexShrink: 0 }}
            />
          </Tooltip>
        </Box>
      }
      subtitle={t('sshConnections.subtitle')}
      actions={
        showActions ? (
          <>
            <Tooltip title={t('sshConnections.systemKey.tooltips.addManual')}>
              <Button variant="outlined" startIcon={<Wifi size={18} />} onClick={onAddManual}>
                {t('sshConnections.systemKey.actions.addManual')}
              </Button>
            </Tooltip>
            <Tooltip title={t('sshConnections.systemKey.tooltips.deploy')}>
              <Button variant="contained" startIcon={<Plus size={18} />} onClick={onDeploy}>
                {t('sshConnections.systemKey.actions.deploy')}
              </Button>
            </Tooltip>
          </>
        ) : undefined
      }
    />
  )
}
