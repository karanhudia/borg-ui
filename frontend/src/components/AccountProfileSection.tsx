import { Box, Button, CircularProgress, Divider, Stack, TextField, Typography } from '@mui/material'

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
  showSetupBanner: boolean
  profileForm: AccountProfileFormData
  deploymentForm: DeploymentProfileFormData
  isSavingProfile: boolean
  isSavingDeployment: boolean
  onProfileFormChange: (updates: Partial<AccountProfileFormData>) => void
  onDeploymentFormChange: (updates: Partial<DeploymentProfileFormData>) => void
  onSaveProfile: () => void
  onSaveDeployment: () => void
}

export default function AccountProfileSection({
  canManageSystem,
  showSetupBanner,
  profileForm,
  deploymentForm,
  isSavingProfile,
  isSavingDeployment,
  onProfileFormChange,
  onDeploymentFormChange,
  onSaveProfile,
  onSaveDeployment,
}: AccountProfileSectionProps) {
  return (
    <Stack spacing={3}>
      {showSetupBanner && (
        <Box
          sx={{
            px: 2,
            py: 1.5,
            border: '1px solid',
            borderColor: 'warning.main',
            borderRadius: 2,
            bgcolor: 'warning.50',
          }}
        >
          <Typography variant="body2" fontWeight={700}>
            Finish account setup
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Change your password first, then update your personal profile details below.
          </Typography>
        </Box>
      )}

      {/* Personal profile */}
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          Personal profile
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Your own identity. Changes here do not affect the system-wide deployment identity.
        </Typography>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSaveProfile()
          }}
        >
          <Stack spacing={2}>
            <TextField
              label="Username"
              value={profileForm.username}
              onChange={(e) => onProfileFormChange({ username: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label="Email"
              type="email"
              value={profileForm.email}
              onChange={(e) => onProfileFormChange({ email: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label="Full name"
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
                {isSavingProfile ? 'Saving…' : 'Save profile'}
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
              Deployment profile
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              System-wide setting. Controls how this deployment presents itself to all users.
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
                    title: 'Individual',
                    body: 'Show admin full name as the account identity.',
                  },
                  {
                    key: 'enterprise',
                    title: 'Enterprise',
                    body: 'Show an organization name as the deployment identity.',
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
                label="Organization name"
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
              {isSavingDeployment ? 'Saving…' : 'Save deployment'}
            </Button>
          </Box>
        </>
      )}
    </Stack>
  )
}
