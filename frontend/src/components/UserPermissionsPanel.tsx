import { useEffect, useState } from 'react'
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
      toast.success('Permission assigned')
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'assign_repository_permission',
        role: addRole,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to assign permission')
    },
  })

  const removeMutation = useMutation({
    mutationFn: (repoId: number) => permissionsAPI.remove(userId!, repoId),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey })
      await syncCurrentUserPermissions()
      toast.success('Permission removed')
      trackSettings(EventAction.DELETE, {
        section: 'users',
        operation: 'remove_repository_permission',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to remove permission')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ repoId, role }: { repoId: number; role: string }) =>
      permissionsAPI.update(userId!, repoId, role),
    onSuccess: async (_, variables) => {
      queryClient.invalidateQueries({ queryKey })
      await syncCurrentUserPermissions()
      toast.success('Permission updated')
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'update_repository_permission',
        role: variables.role,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update permission')
    },
  })

  const updateScopeMutation = useMutation({
    mutationFn: (role: string | null) => permissionsAPI.updateScope(userId!, role),
    onSuccess: async (_, nextRole) => {
      queryClient.invalidateQueries({ queryKey: scopeQueryKey })
      setWildcardRole(nextRole ?? '')
      await syncCurrentUserPermissions()
      toast.success(nextRole ? 'Automatic access updated' : 'Automatic access cleared')
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'update_repository_scope',
        role: nextRole ?? 'none',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update automatic access')
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
          Repository scope
        </Typography>
        {canManageAssignments ? (
          <Stack spacing={1.25}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              alignItems={{ xs: 'stretch', sm: 'center' }}
              justifyContent="space-between"
            >
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
                sx={{ flexWrap: 'wrap' }}
              >
                <ToggleButton value="all">All repositories</ToggleButton>
                <ToggleButton value="selected">Selected repositories only</ToggleButton>
              </ToggleButtonGroup>
              <Button
                size="small"
                variant="contained"
                disabled={
                  updateScopeMutation.isPending ||
                  (scopeMode === 'all' ? effectiveWildcardRole : null) === wildcardValue
                }
                onClick={() => updateScopeMutation.mutate(scopeRoleToSave)}
                sx={{
                  alignSelf: { xs: 'flex-end', sm: 'center' },
                  minWidth: 0,
                  px: 1.3,
                  py: 0.65,
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'none',
                  borderRadius: 999,
                  boxShadow: 'none',
                  bgcolor: 'success.main',
                  color: 'success.contrastText',
                  '&:hover': {
                    boxShadow: 'none',
                    bgcolor: 'success.dark',
                  },
                  '&.Mui-disabled': {
                    bgcolor: 'action.disabledBackground',
                    color: 'text.disabled',
                  },
                }}
              >
                Save changes
              </Button>
            </Stack>
            {scopeMode === 'all' ? (
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <FormControl size="small" sx={{ minWidth: 170 }}>
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
                  New repositories inherit this automatically.
                </Typography>
              </Stack>
            ) : (
              <Typography variant="caption" color="text.secondary">
                Use this when you want to limit access to a few repositories only.
              </Typography>
            )}
          </Stack>
        ) : hasAutomaticAccess ? (
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              label={`Automatic ${formatRoleLabel(wildcardValue)} access`}
              color={ROLE_COLOR[wildcardValue ?? 'viewer'] ?? 'default'}
              size="small"
            />
            <Typography variant="caption" color="text.secondary">
              Future repositories inherit this access automatically.
            </Typography>
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Restricted access. This user only sees repositories assigned below.
          </Typography>
        )}
      </Box>

      {/* Assigned permissions */}
      {scopeMode === 'all' ? (
        <Box sx={{ px: 2.5, py: 2.5 }}>
          {canManageAssignments ? (
            <Alert severity="info" variant="outlined">
              This user currently has access to all repositories as{' '}
              <strong>{effectiveWildcardRole}</strong>. Switch to selected repositories only if you
              want to restrict them.
            </Alert>
          ) : (
            <Alert severity="info" variant="outlined">
              This account currently has automatic access to all repositories as{' '}
              <strong>{formatRoleLabel(wildcardValue)}</strong>.
            </Alert>
          )}
        </Box>
      ) : permissions.length === 0 ? (
        <Box sx={{ px: 2.5, py: 2.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <ShieldOff size={15} style={{ opacity: 0.35, flexShrink: 0 }} />
          <Typography variant="body2" color="text.secondary">
            {hasAutomaticAccess
              ? 'No repository-specific assignments. Automatic access covers current and future repositories.'
              : 'No repository permissions assigned yet.'}
          </Typography>
        </Box>
      ) : (
        <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
          <Box component="thead">
            <Box component="tr" sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
              {(['Repository', 'Role', canManageAssignments ? '' : null] as (string | null)[])
                .filter(Boolean)
                .map((h) => (
                  <Box
                    key={String(h)}
                    component="th"
                    sx={{
                      px: 1.5,
                      py: 1,
                      textAlign: 'left',
                      typography: 'caption',
                      fontWeight: 700,
                      color: 'text.secondary',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {h}
                  </Box>
                ))}
            </Box>
          </Box>
          <Box component="tbody">
            {permissions.map((perm) => (
              <Box
                key={perm.id}
                component="tr"
                sx={{ '&:not(:last-child)': { borderBottom: '1px solid', borderColor: 'divider' } }}
              >
                <Box component="td" sx={{ px: 1.5, py: 1.25 }}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Database size={13} style={{ opacity: 0.4, flexShrink: 0 }} />
                    <Typography variant="body2">{perm.repository_name}</Typography>
                  </Stack>
                </Box>
                <Box component="td" sx={{ px: 1.5, py: 1.25 }}>
                  {canManageAssignments ? (
                    <FormControl size="small" sx={{ minWidth: 130 }}>
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
                </Box>
                {canManageAssignments && (
                  <Box component="td" sx={{ px: 1.5, py: 1.25, textAlign: 'right' }}>
                    <Tooltip title="Remove access">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => removeMutation.mutate(perm.repository_id)}
                        disabled={removeMutation.isPending}
                        sx={{
                          borderRadius: 1,
                          opacity: 0.45,
                          transition: 'opacity 140ms ease, background-color 140ms ease',
                          '&:hover': { opacity: 1, bgcolor: 'rgba(239,68,68,0.12)' },
                        }}
                      >
                        <Trash2 size={14} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                )}
              </Box>
            ))}
          </Box>
        </Box>
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
            Grant access
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
                No repositories configured. Add a repository first.
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
                All repositories are already assigned to this user.
              </Typography>
            </Box>
          ) : (
            <Stack direction="row" spacing={1} alignItems="center">
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <Select
                  value={addRepoId}
                  onChange={(e) => setAddRepoId(e.target.value as number)}
                  displayEmpty
                >
                  <MenuItem value="" disabled>
                    Select repository
                  </MenuItem>
                  {availableRepos.map((r) => (
                    <MenuItem key={r.id} value={r.id}>
                      {r.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 110 }}>
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
              >
                Assign
              </Button>
            </Stack>
          )}
        </Box>
      )}
    </Box>
  )
}
