import React from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { AlertCircle, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatRoleLabel } from '../../utils/rolePresentation'
import ResponsiveDialog from '../ResponsiveDialog'
import UserPermissionsPanel from '../UserPermissionsPanel'
import { PasswordFormState, UserFormState, UserType } from './types'

type RolePresentation = {
  label: string
  color: 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'
  isAdminRole: boolean
  isOperatorRole: boolean
}

interface RepositoryAccessDialogProps {
  accessUser: UserType | null
  selectedAccessUserId: number | null
  repositories: Array<{ id: number; name: string }>
  getRolePresentation: (role: string) => RolePresentation
  roleHasGlobalPermission: (role: string, permission: string) => boolean
  onClose: () => void
}

export const RepositoryAccessDialog: React.FC<RepositoryAccessDialogProps> = ({
  accessUser,
  selectedAccessUserId,
  repositories,
  getRolePresentation,
  roleHasGlobalPermission,
  onClose,
}) => {
  const { t } = useTranslation()

  const getRepositoryAccessSummary = (user: UserType) => {
    if (getRolePresentation(user.role).isAdminRole) {
      return t('settings.users.accessSummary.adminRole')
    }
    if (user.all_repositories_role) {
      return t('settings.users.accessSummary.defaultAccess', {
        role: formatRoleLabel(user.all_repositories_role),
      })
    }
    return t('settings.users.accessSummary.restricted')
  }

  return (
    <ResponsiveDialog open={!!accessUser} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        <Typography variant="h6" fontWeight={600} lineHeight={1.2}>
          {t('settings.users.repositoryAccess.title')}
        </Typography>
        {accessUser && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {accessUser.full_name || accessUser.username}
          </Typography>
        )}
      </DialogTitle>
      <DialogContent>
        {accessUser && (
          <Stack spacing={2.5} sx={{ pt: 1, pb: 1 }}>
            <Box>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                <ShieldCheck size={14} style={{ opacity: 0.6 }} />
                <Typography variant="body2" fontWeight={600}>
                  {getRolePresentation(accessUser.role).label}
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {getRepositoryAccessSummary(accessUser)}
              </Typography>
            </Box>
            <Divider />
            {roleHasGlobalPermission(accessUser.role, 'repositories.manage_all') ? (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  px: 2,
                  py: 1.75,
                  borderRadius: 2,
                  border: '1px solid',
                  borderColor: 'rgba(124,58,237,0.2)',
                  bgcolor: 'rgba(124,58,237,0.05)',
                }}
              >
                <ShieldCheck size={15} style={{ color: '#7c3aed', flexShrink: 0 }} />
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    {t('settings.users.repositoryAccess.globalAccess')}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t('settings.users.repositoryAccess.globalAccessDesc')}
                  </Typography>
                </Box>
              </Box>
            ) : (
              <UserPermissionsPanel
                userId={selectedAccessUserId ?? accessUser.id}
                canManageAssignments={true}
                repositories={repositories}
                targetUserRole={accessUser.role}
              />
            )}
          </Stack>
        )}
      </DialogContent>
    </ResponsiveDialog>
  )
}

interface UserFormDialogProps {
  open: boolean
  editingUser: UserType | null
  userForm: UserFormState
  userOidcFieldsExposed: boolean
  onUserFormChange: (userForm: UserFormState) => void
  onClose: () => void
  onSubmit: (e: React.FormEvent) => void
}

export const UserFormDialog: React.FC<UserFormDialogProps> = ({
  open,
  editingUser,
  userForm,
  userOidcFieldsExposed,
  onUserFormChange,
  onClose,
  onSubmit,
}) => {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {editingUser
          ? t('settings.users.editDialog.title')
          : t('settings.users.createDialog.title')}
      </DialogTitle>
      <form onSubmit={onSubmit}>
        <DialogContent>
          <Stack spacing={3}>
            <TextField
              label={t('settings.users.fields.username')}
              value={userForm.username}
              onChange={(e) => onUserFormChange({ ...userForm, username: e.target.value })}
              required
              fullWidth
            />

            <TextField
              label={t('settings.users.fields.email')}
              type="email"
              value={userForm.email}
              onChange={(e) => onUserFormChange({ ...userForm, email: e.target.value })}
              required
              fullWidth
            />

            {!editingUser && (
              <TextField
                label={t('settings.users.fields.password')}
                type="password"
                value={userForm.password}
                onChange={(e) => onUserFormChange({ ...userForm, password: e.target.value })}
                required
                fullWidth
              />
            )}

            <TextField
              label={t('settings.users.fields.fullName')}
              value={userForm.full_name}
              onChange={(e) => onUserFormChange({ ...userForm, full_name: e.target.value })}
              fullWidth
            />

            <FormControl fullWidth>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                {t('settings.users.fields.role')}
              </Typography>
              <Select
                value={userForm.role}
                onChange={(e) => onUserFormChange({ ...userForm, role: e.target.value })}
                size="small"
              >
                <MenuItem value="admin">{t('settings.users.roles.adminDescription')}</MenuItem>
                <MenuItem value="operator">
                  {t('settings.users.roles.operatorDescription')}
                </MenuItem>
                <MenuItem value="viewer">{t('settings.users.roles.viewerDescription')}</MenuItem>
              </Select>
            </FormControl>

            {editingUser && userOidcFieldsExposed && (
              <>
                <Alert severity="info">
                  <Typography variant="body2">
                    {t('settings.users.ssoIdentity.selfLinkHint')}
                  </Typography>
                </Alert>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', sm: '180px 1fr' },
                    gap: 2,
                  }}
                >
                  <TextField
                    select
                    label={t('settings.users.fields.authSource')}
                    value={userForm.auth_source}
                    onChange={(e) =>
                      onUserFormChange({
                        ...userForm,
                        auth_source: e.target.value,
                        oidc_subject: e.target.value === 'oidc' ? userForm.oidc_subject : '',
                      })
                    }
                    fullWidth
                  >
                    <MenuItem value="local">{t('settings.users.authSources.local')}</MenuItem>
                    <MenuItem value="oidc">{t('settings.users.authSources.oidc')}</MenuItem>
                  </TextField>
                  <TextField
                    label={t('settings.users.fields.oidcSubject')}
                    value={userForm.oidc_subject}
                    onChange={(e) =>
                      onUserFormChange({ ...userForm, oidc_subject: e.target.value })
                    }
                    disabled={userForm.auth_source !== 'oidc'}
                    helperText={
                      userForm.auth_source === 'oidc'
                        ? t('settings.users.ssoIdentity.subjectHelper')
                        : t('settings.users.ssoIdentity.clearHelper')
                    }
                    fullWidth
                  />
                </Box>
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('settings.users.buttons.cancel')}</Button>
          <Button type="submit" variant="contained">
            {editingUser ? t('settings.users.buttons.update') : t('settings.users.buttons.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}

interface PasswordResetDialogProps {
  open: boolean
  passwordForm: PasswordFormState
  onPasswordFormChange: (passwordForm: PasswordFormState) => void
  onClose: () => void
  onSubmit: (e: React.FormEvent) => void
}

export const PasswordResetDialog: React.FC<PasswordResetDialogProps> = ({
  open,
  passwordForm,
  onPasswordFormChange,
  onClose,
  onSubmit,
}) => {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('settings.users.resetPasswordDialog.title')}</DialogTitle>
      <form onSubmit={onSubmit}>
        <DialogContent>
          <TextField
            label={t('settings.password.new')}
            type="password"
            value={passwordForm.new_password}
            onChange={(e) => onPasswordFormChange({ new_password: e.target.value })}
            required
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('settings.users.buttons.cancel')}</Button>
          <Button type="submit" variant="contained">
            {t('settings.users.actions.resetPassword')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}

interface DeleteUserDialogProps {
  user: UserType | null
  isDeleting: boolean
  onClose: () => void
  onDelete: () => void
}

export const DeleteUserDialog: React.FC<DeleteUserDialogProps> = ({
  user,
  isDeleting,
  onClose,
  onDelete,
}) => {
  const { t } = useTranslation()

  return (
    <Dialog open={!!user} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={2} alignItems="center">
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: '50%',
              backgroundColor: 'error.lighter',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <AlertCircle size={24} color="#d32f2f" />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            {t('settings.users.deleteDialog.title')}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2">
          {t('settings.users.deleteDialog.message', { username: user?.username })}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {t('settings.users.deleteDialog.warning')}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('settings.users.buttons.cancel')}</Button>
        <Button
          onClick={onDelete}
          variant="contained"
          color="error"
          disabled={isDeleting}
          startIcon={isDeleting ? <CircularProgress size={16} /> : null}
        >
          {isDeleting
            ? t('settings.users.deleteDialog.deleting')
            : t('settings.users.deleteDialog.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
