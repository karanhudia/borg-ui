import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  CircularProgress,
  Chip,
  IconButton,
  Select,
  MenuItem,
  FormControl,
  Button,
  Stack,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Alert,
} from '@mui/material'
import { Trash2, Plus, Database, ShieldOff } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { permissionsAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { useAuthorization } from '../hooks/useAuthorization'
import { formatRoleLabel } from '../utils/rolePresentation'

interface Permission {
  id: number
  user_id: number
  repository_id: number
  repository_name: string
  role: string
  created_at: string
}

interface Repository {
  id: number
  name: string
}

interface UserPermissionsPanelProps {
  /** If undefined, loads the current user's own permissions (read-only for non-admins) */
  userId?: number
  /** Whether editing controls are shown */
  canManageAssignments?: boolean
  /** Repositories available for assignment — only needed when editing is enabled */
  repositories?: Repository[]
  /** The target user's global role — caps available role options in the selector */
  targetUserRole?: string
  /** Title shown in the header bar */
  title?: string
  /** Subtitle shown below the title */
  subtitle?: string
}

const ROLE_COLOR: Record<string, 'error' | 'info' | 'default'> = {
  admin: 'error',
  operator: 'info',
  viewer: 'default',
}

export default function UserPermissionsPanel({
  userId,
  canManageAssignments = false,
  repositories = [],
  targetUserRole = 'operator',
  title,
  subtitle,
}: UserPermissionsPanelProps) {
  const { t } = useTranslation()
  const { assignableRepositoryRolesFor } = useAuthorization()
  const { user: currentUser, refreshUser } = useAuth()
  const availableRoles = assignableRepositoryRolesFor(targetUserRole)
  const queryClient = useQueryClient()
  const { trackSettings, EventAction } = useAnalytics()
  const [addRepoId, setAddRepoId] = useState<number | ''>('')
  const [addRole, setAddRole] = useState('viewer')
  const [wildcardRole, setWildcardRole] = useState<string>('')
  const [scopeMode, setScopeMode] = useState<'all' | 'selected'>('selected')

  const queryKey = userId ? ['user-permissions', userId] : ['my-permissions']
  const scopeQueryKey = userId ? ['user-permission-scope', userId] : ['my-permission-scope']
  const isCurrentUserTarget = userId == null || userId === currentUser?.id

  const syncCurrentUserPermissions = async () => {
    if (!isCurrentUserTarget) return
    queryClient.invalidateQueries({ queryKey: ['my-permissions'] })
    queryClient.invalidateQueries({ queryKey: ['my-permission-scope'] })
    await refreshUser()
  }

  const { data: permissions = [], isLoading } = useQuery<Permission[]>({
    queryKey,
    queryFn: () =>
      userId
        ? permissionsAPI.getUserPermissions(userId).then((r) => r.data)
        : permissionsAPI.getMyPermissions().then((r) => r.data),
  })
  const { data: permissionScope, isLoading: isScopeLoading } = useQuery({
    queryKey: scopeQueryKey,
    queryFn: () =>
      userId
        ? permissionsAPI.getUserPermissionScope(userId).then((r) => r.data)
        : permissionsAPI.getMyPermissionScope().then((r) => r.data),
  })

  const assignMutation = useMutation({
    mutationFn: ({ repoId, role }: { repoId: number; role: string }) =>
      permissionsAPI.assign(userId!, { repository_id: repoId, role }),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey })
      setAddRepoId('')
      setAddRole('viewer')
      await syncCurrentUserPermissions()
      toast.success(t('settings.permissions.toasts.assigned'))
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'assign_repository_permission',
        role: addRole,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || t('settings.permissions.toasts.failedToAssign'))
    },
  })

  const removeMutation = useMutation({
    mutationFn: (repoId: number) => permissionsAPI.remove(userId!, repoId),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey })
      await syncCurrentUserPermissions()
      toast.success(t('settings.permissions.toasts.removed'))
      trackSettings(EventAction.DELETE, {
        section: 'users',
        operation: 'remove_repository_permission',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || t('settings.permissions.toasts.failedToRemove'))
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ repoId, role }: { repoId: number; role: string }) =>
      permissionsAPI.update(userId!, repoId, role),
    onSuccess: async (_, variables) => {
      queryClient.invalidateQueries({ queryKey })
      await syncCurrentUserPermissions()
      toast.success(t('settings.permissions.toasts.updated'))
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'update_repository_permission',
        role: variables.role,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || t('settings.permissions.toasts.failedToUpdate'))
    },
  })

  const updateScopeMutation = useMutation({
    mutationFn: (role: string | null) => permissionsAPI.updateScope(userId!, role),
    onSuccess: async (_, nextRole) => {
      queryClient.invalidateQueries({ queryKey: scopeQueryKey })
      setWildcardRole(nextRole ?? '')
      await syncCurrentUserPermissions()
      toast.success(
        nextRole
          ? t('settings.permissions.toasts.automaticUpdated')
          : t('settings.permissions.toasts.automaticCleared')
      )
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'update_repository_scope',
        role: nextRole ?? 'none',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        error.response?.data?.detail || t('settings.permissions.toasts.failedToUpdateAutomatic')
      )
    },
  })

  useEffect(() => {
    const nextWildcardRole = permissionScope?.all_repositories_role ?? ''
    setWildcardRole(nextWildcardRole)
    setScopeMode(nextWildcardRole ? 'all' : 'selected')
  }, [permissionScope?.all_repositories_role])

  if (isLoading || isScopeLoading) {
    return (
      <Box sx={{ p: 2 }}>
        <CircularProgress size={20} />
      </Box>
    )
  }

  const assignedRepoIds = new Set(permissions.map((p) => p.repository_id))
  const availableRepos = repositories.filter((r) => !assignedRepoIds.has(r.id))
  const allAssigned = repositories.length > 0 && availableRepos.length === 0
  const noReposConfigured = repositories.length === 0
  const wildcardValue = permissionScope?.all_repositories_role ?? null
  const hasAutomaticAccess = Boolean(wildcardValue)
  const defaultRoleForScope = availableRoles[availableRoles.length - 1] ?? 'viewer'
  const effectiveWildcardRole = wildcardRole || defaultRoleForScope
  const scopeRoleToSave = scopeMode === 'all' ? effectiveWildcardRole : null

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
        overflow: 'hidden',
      }}
    >
      {/* Header — matches ApiTokensSection pattern */}
      {title && (
        <Box
          sx={{
            px: 2.5,
            py: 2,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'action.hover',
          }}
        >
          <Typography variant="body2" fontWeight={600}>
            {title}
          </Typography>
          {subtitle && (
            <Typography variant="caption" color="text.secondary">
              {subtitle}
            </Typography>
          )}
        </Box>
      )}

      <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Typography
          variant="caption"
          fontWeight={700}
          color="text.secondary"
          sx={{
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            fontSize: '0.68rem',
            display: 'block',
            mb: 1.25,
          }}
        >
          {t('settings.permissions.scope.title')}
        </Typography>
        {canManageAssignments ? (
          <Stack spacing={1.25}>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={scopeMode}
              onChange={(_, nextValue) => {
                if (nextValue) {
                  setScopeMode(nextValue)
                  if (nextValue === 'all' && !wildcardRole) {
                    setWildcardRole(defaultRoleForScope)
                  }
                }
              }}
              sx={{ width: '100%' }}
            >
              <ToggleButton value="all" sx={{ flex: 1 }}>
                {t('settings.permissions.scope.allRepositories')}
              </ToggleButton>
              <ToggleButton value="selected" sx={{ flex: 1 }}>
                {t('settings.permissions.scope.selectedOnly')}
              </ToggleButton>
            </ToggleButtonGroup>
            {scopeMode === 'all' ? (
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                alignItems={{ xs: 'flex-start', sm: 'center' }}
              >
                <FormControl size="small" sx={{ minWidth: { xs: '100%', sm: 170 } }}>
                  <Select
                    value={effectiveWildcardRole}
                    onChange={(e) => setWildcardRole(e.target.value)}
                  >
                    {availableRoles.map((r) => (
                      <MenuItem key={r} value={r}>
                        {formatRoleLabel(r)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Typography variant="caption" color="text.secondary">
                  {t('settings.permissions.scope.autoInheritHint')}
                </Typography>
              </Stack>
            ) : (
              <Typography variant="caption" color="text.secondary">
                {t('settings.permissions.scope.restrictedHint')}
              </Typography>
            )}
          </Stack>
        ) : hasAutomaticAccess ? (
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              label={t('settings.permissions.scope.automaticAccess', {
                role: formatRoleLabel(wildcardValue),
              })}
              color={ROLE_COLOR[wildcardValue ?? 'viewer'] ?? 'default'}
              size="small"
            />
            <Typography variant="caption" color="text.secondary">
              {t('settings.permissions.scope.futureInheritHint')}
            </Typography>
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t('settings.permissions.scope.restrictedAccess')}
          </Typography>
        )}
      </Box>

      {/* Assigned permissions — min-height prevents jarky dialog resize when switching tabs */}
      <Box sx={{ minHeight: 160 }}>
        {scopeMode === 'all' ? (
          <Box sx={{ px: 2.5, py: 2.5 }}>
            {canManageAssignments ? (
              <Alert severity="info" variant="outlined">
                {t('settings.permissions.alert.allAccessPrefix')}{' '}
                <strong>{effectiveWildcardRole}</strong>
                {t('settings.permissions.alert.allAccessSuffix')}
              </Alert>
            ) : (
              <Alert severity="info" variant="outlined">
                {t('settings.permissions.alert.automaticAccessPrefix')}{' '}
                <strong>{formatRoleLabel(wildcardValue)}</strong>.
              </Alert>
            )}
          </Box>
        ) : permissions.length === 0 ? (
          <Box sx={{ px: 2.5, py: 2.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <ShieldOff size={15} style={{ opacity: 0.35, flexShrink: 0 }} />
            <Typography variant="body2" color="text.secondary">
              {hasAutomaticAccess
                ? t('settings.permissions.empty.automaticCoverage')
                : t('settings.permissions.empty.noPermissions')}
            </Typography>
          </Box>
        ) : (
          <Stack>
            {permissions.map((perm) => (
              <Box
                key={perm.id}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 1.5,
                  py: 1.25,
                  '&:not(:last-child)': { borderBottom: '1px solid', borderColor: 'divider' },
                }}
              >
                <Stack
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  sx={{ flex: 1, minWidth: 0 }}
                >
                  <Database size={13} style={{ opacity: 0.4, flexShrink: 0 }} />
                  <Typography variant="body2" noWrap>
                    {perm.repository_name}
                  </Typography>
                </Stack>
                {canManageAssignments ? (
                  <FormControl size="small" sx={{ minWidth: { xs: 96, sm: 120 }, flexShrink: 0 }}>
                    <Select
                      value={perm.role}
                      onChange={(e) =>
                        updateMutation.mutate({
                          repoId: perm.repository_id,
                          role: e.target.value,
                        })
                      }
                      disabled={updateMutation.isPending}
                    >
                      {availableRoles.map((r) => (
                        <MenuItem key={r} value={r}>
                          {formatRoleLabel(r)}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : (
                  <Chip
                    label={formatRoleLabel(perm.role)}
                    color={ROLE_COLOR[perm.role] ?? 'default'}
                    size="small"
                  />
                )}
                {canManageAssignments && (
                  <Tooltip title={t('settings.permissions.actions.removeAccess')}>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => removeMutation.mutate(perm.repository_id)}
                      disabled={removeMutation.isPending}
                      sx={{
                        borderRadius: 1,
                        opacity: 0.45,
                        flexShrink: 0,
                        transition: 'opacity 140ms ease, background-color 140ms ease',
                        '&:hover': { opacity: 1, bgcolor: 'rgba(239,68,68,0.12)' },
                      }}
                    >
                      <Trash2 size={14} />
                    </IconButton>
                  </Tooltip>
                )}
              </Box>
            ))}
          </Stack>
        )}

        {/* Grant access section — admin only */}
        {canManageAssignments && scopeMode === 'selected' && (
          <Box sx={{ px: 2.5, py: 2, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography
              variant="caption"
              fontWeight={700}
              color="text.secondary"
              sx={{
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
                fontSize: '0.68rem',
                display: 'block',
                mb: 1.25,
              }}
            >
              {t('settings.permissions.grantAccess.title')}
            </Typography>

            {noReposConfigured ? (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  px: 2,
                  py: 1.75,
                  borderRadius: 2,
                  border: '1px dashed',
                  borderColor: 'divider',
                }}
              >
                <Database size={15} style={{ opacity: 0.35, flexShrink: 0 }} />
                <Typography variant="body2" color="text.secondary">
                  {t('settings.permissions.grantAccess.noRepositories')}
                </Typography>
              </Box>
            ) : allAssigned ? (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  px: 2,
                  py: 1.75,
                  borderRadius: 2,
                  border: '1px dashed',
                  borderColor: 'divider',
                }}
              >
                <ShieldOff size={15} style={{ opacity: 0.35, flexShrink: 0 }} />
                <Typography variant="body2" color="text.secondary">
                  {t('settings.permissions.grantAccess.allAssigned')}
                </Typography>
              </Box>
            ) : (
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                alignItems={{ xs: 'stretch', sm: 'center' }}
              >
                <FormControl size="small" sx={{ flex: 1, minWidth: { sm: 160 } }}>
                  <Select
                    value={addRepoId}
                    onChange={(e) => setAddRepoId(e.target.value as number)}
                    displayEmpty
                  >
                    <MenuItem value="" disabled>
                      {t('settings.permissions.grantAccess.selectRepository')}
                    </MenuItem>
                    {availableRepos.map((r) => (
                      <MenuItem key={r.id} value={r.id}>
                        {r.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Stack direction="row" spacing={1} alignItems="center">
                  <FormControl size="small" sx={{ minWidth: 110, flex: { xs: 1, sm: 'none' } }}>
                    <Select value={addRole} onChange={(e) => setAddRole(e.target.value)}>
                      {availableRoles.map((r) => (
                        <MenuItem key={r} value={r}>
                          {formatRoleLabel(r)}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={
                      assignMutation.isPending ? <CircularProgress size={12} /> : <Plus size={14} />
                    }
                    disabled={!addRepoId || assignMutation.isPending}
                    onClick={() => {
                      if (addRepoId)
                        assignMutation.mutate({ repoId: addRepoId as number, role: addRole })
                    }}
                    sx={{ flexShrink: 0 }}
                  >
                    {t('settings.permissions.grantAccess.assign')}
                  </Button>
                </Stack>
              </Stack>
            )}
          </Box>
        )}
      </Box>

      {/* Shared save footer — scope changes only, hidden when up to date */}
      {canManageAssignments && (
        <Box
          sx={{
            px: 2.5,
            py: 1.5,
            borderTop: '1px solid',
            borderColor: 'divider',
            display: 'flex',
            justifyContent: { xs: 'stretch', sm: 'flex-end' },
          }}
        >
          <Button
            size="small"
            variant="contained"
            disabled={
              updateScopeMutation.isPending ||
              (scopeMode === 'all' ? effectiveWildcardRole : null) === wildcardValue
            }
            onClick={() => updateScopeMutation.mutate(scopeRoleToSave)}
            sx={{
              flex: { xs: 1, sm: 'none' },
              minWidth: 0,
              px: 2,
              py: 0.65,
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: 999,
              boxShadow: 'none',
              bgcolor: 'success.main',
              color: 'success.contrastText',
              '&:hover': { boxShadow: 'none', bgcolor: 'success.dark' },
              '&.Mui-disabled': {
                bgcolor: 'action.disabledBackground',
                color: 'text.disabled',
              },
            }}
          >
            {t('settings.permissions.saveChanges')}
          </Button>
        </Box>
      )}
    </Box>
  )
}
