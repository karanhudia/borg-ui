import {
  Alert,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../components/shared/ResponsiveDialog'
import type { AgentMachineResponse } from '../../services/api'
import CopyableCodeBlock from './CopyableCodeBlock'

/**
 * Hands the operator the one command that removes Borg UI from an endpoint.
 *
 * No typed confirmation: the command still has to be pasted into a root shell
 * on the target machine, which is confirmation enough (spec section 7). What
 * the dialog owes the operator instead is an honest inventory, and the two
 * lines saying what is not touched.
 */
export default function AgentUninstallDialog({
  agent,
  open,
  serverUrl,
  onCopy,
  onCancel,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  serverUrl: string
  onCopy: (value: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const command = `curl -fsSL ${serverUrl}/agent/uninstall.sh | sudo bash`

  const removals = [
    t('managedAgents.page.uninstallDialog.removesService'),
    t('managedAgents.page.uninstallDialog.removesVenv'),
    t('managedAgents.page.uninstallDialog.removesConfig'),
    t('managedAgents.page.uninstallDialog.removesUser'),
  ]

  return (
    <ResponsiveDialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="md"
      footer={
        <DialogActions>
          <Button onClick={onCancel}>{t('common.buttons.close')}</Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.uninstallDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Stack spacing={0.5}>
            <Typography sx={{ fontWeight: 700 }}>
              {[agent?.name, agent?.hostname].filter(Boolean).join(' · ')}
            </Typography>
            <Typography sx={{ color: 'text.secondary' }}>
              {t('managedAgents.page.uninstallDialog.description')}
            </Typography>
          </Stack>
          <CopyableCodeBlock
            value={command}
            copyLabel={t('managedAgents.page.uninstallDialog.copyCommand')}
            onCopy={() => onCopy(command)}
          />
          <Stack spacing={0.5}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              {t('managedAgents.page.uninstallDialog.removesTitle')}
            </Typography>
            <List dense disablePadding>
              {removals.map((line) => (
                <ListItem key={line} disableGutters sx={{ py: 0 }}>
                  <ListItemText
                    primary={line}
                    slotProps={{
                      primary: { variant: 'body2', color: 'text.secondary' },
                    }}
                  />
                </ListItem>
              ))}
            </List>
          </Stack>
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.uninstallDialog.keepsBorg')}{' '}
            {t('managedAgents.page.uninstallDialog.keepsRepositories')}
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
