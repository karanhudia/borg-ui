import { Box, Button, CircularProgress, Divider, Stack, TextField, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import AccountSecuritySection from './AccountSecuritySection'

export interface AccountProfileFormData {
  username: string
  email: string
  full_name: string
}

export interface DeploymentProfileFormData {
  deployment_type: 'individual' | 'enterprise'
  enterprise_name: string
}

interface AccountProfileSectionProps {
  canManageSystem: boolean
  mustChangePassword: boolean
  profileForm: AccountProfileFormData
  deploymentForm: DeploymentProfileFormData
  isSavingProfile: boolean
  isSavingDeployment: boolean
  onProfileFormChange: (updates: Partial<AccountProfileFormData>) => void
  onDeploymentFormChange: (updates: Partial<DeploymentProfileFormData>) => void
  onSaveProfile: () => void
  onSaveDeployment: () => void
  onOpenChangePassword: () => void
}

export default function AccountProfileSection({
  canManageSystem,
  mustChangePassword,
  profileForm,
  deploymentForm,
  isSavingProfile,
  isSavingDeployment,
  onProfileFormChange,
  onDeploymentFormChange,
  onSaveProfile,
  onSaveDeployment,
  onOpenChangePassword,
}: AccountProfileSectionProps) {
  const { t } = useTranslation()

  const passwordSection = (
    <Box>
      <Typography variant="subtitle2" fontWeight={700} gutterBottom>
        {t('settings.account.security.accountPassword')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {mustChangePassword
          ? t('settings.account.security.passwordUpdateHint')
          : t('settings.account.security.changeCredentialsHint')}
      </Typography>
      <AccountSecuritySection
        mustChangePassword={mustChangePassword}
        onOpenChangePassword={onOpenChangePassword}
      />
    </Box>
  )

  return (
    <Stack spacing={3}>
      {mustChangePassword && passwordSection}

      {mustChangePassword && <Divider />}

      {/* Personal profile */}
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          {t('settings.account.profile.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('settings.account.profile.description')}
        </Typography>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSaveProfile()
          }}
        >
          <Stack spacing={2}>
            <TextField
              label={t('settings.users.fields.username')}
              value={profileForm.username}
              onChange={(e) => onProfileFormChange({ username: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label={t('settings.users.fields.email')}
              type="email"
              value={profileForm.email}
              onChange={(e) => onProfileFormChange({ email: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label={t('settings.users.fields.fullName')}
              value={profileForm.full_name}
              onChange={(e) => onProfileFormChange({ full_name: e.target.value })}
              fullWidth
              size="small"
            />
            <Box>
              <Button
                type="submit"
                variant="contained"
                disabled={isSavingProfile}
                startIcon={isSavingProfile ? <CircularProgress size={14} /> : null}
              >
                {isSavingProfile
                  ? t('settings.account.profile.saving')
                  : t('settings.account.profile.saveButton')}
              </Button>
            </Box>
          </Stack>
        </form>
      </Box>

      {canManageSystem && (
        <>
          <Divider />

          {/* Deployment profile */}
          <Box>
            <Typography variant="subtitle2" fontWeight={700} gutterBottom>
              {t('settings.account.profile.deployment.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t('settings.account.profile.deployment.description')}
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
                gap: 1.5,
                mb: 2,
              }}
            >
              {(
                [
                  {
                    key: 'individual',
                    title: t('settings.account.profile.deployment.individual'),
                    body: t('settings.account.profile.deployment.individualDesc'),
                  },
                  {
                    key: 'enterprise',
                    title: t('settings.account.profile.deployment.enterprise'),
                    body: t('settings.account.profile.deployment.enterpriseDesc'),
                  },
                ] as const
              ).map((option) => (
                <Box
                  key={option.key}
                  onClick={() => onDeploymentFormChange({ deployment_type: option.key })}
                  sx={{
                    p: 2,
                    border: '1px solid',
                    borderColor:
                      deploymentForm.deployment_type === option.key ? 'primary.main' : 'divider',
                    borderRadius: 2,
                    cursor: 'pointer',
                    bgcolor:
                      deploymentForm.deployment_type === option.key
                        ? 'rgba(8,145,178,0.06)'
                        : 'transparent',
                    transition: 'border-color 160ms ease, background-color 160ms ease',
                  }}
                >
                  <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                    {option.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {option.body}
                  </Typography>
                </Box>
              ))}
            </Box>
            {deploymentForm.deployment_type === 'enterprise' && (
              <TextField
                label={t('settings.account.profile.deployment.orgName')}
                value={deploymentForm.enterprise_name}
                onChange={(e) => onDeploymentFormChange({ enterprise_name: e.target.value })}
                fullWidth
                size="small"
                sx={{ mb: 2 }}
              />
            )}
            <Button
              variant="contained"
              disabled={
                isSavingDeployment ||
                (deploymentForm.deployment_type === 'enterprise' &&
                  !deploymentForm.enterprise_name.trim())
              }
              startIcon={isSavingDeployment ? <CircularProgress size={14} /> : null}
              onClick={onSaveDeployment}
            >
              {isSavingDeployment
                ? t('settings.account.profile.saving')
                : t('settings.account.profile.deployment.saveButton')}
            </Button>
          </Box>
        </>
      )}

      <Divider />

      {!mustChangePassword && passwordSection}
    </Stack>
  )
}
