import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Box, Typography, IconButton, Tooltip, Skeleton, alpha, useTheme } from '@mui/material'
import { HardDrive, XCircle, Trash2, FolderOpen, Copy, Info } from 'lucide-react'
import { mountsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import { formatDate } from '../utils/dateUtils'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'

interface Mount {
  mount_id: string
  mount_point: string
  mount_type: string
  source: string
  created_at: string
  job_id: number | null
  repository_id: number | null
  connection_id: number | null
}

function MountCardSkeleton({ index = 0 }: { index?: number }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const desktopGridTemplate = 'minmax(0, 1.2fr) minmax(0, 1fr) 180px 100px'

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: desktopGridTemplate,
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 1.125,
        borderBottom: '1px solid',
        borderBottomColor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.04),
        opacity: 0,
        animation: 'mountSkeletonFadeIn 0.35s ease forwards',
        animationDelay: `${index * 40}ms`,
        '@keyframes mountSkeletonFadeIn': {
          from: { opacity: 0 },
          to: { opacity: 1 },
        },
        '@media (max-width: 767px)': {
          display: 'flex',
          flexWrap: 'wrap',
          gap: 0.75,
          px: 1.75,
          py: 1.25,
        },
      }}
    >
      <Box>
        <Skeleton
          variant="text"
          width={[160, 200, 140, 180, 152][index % 5]}
          height={16}
          sx={{ borderRadius: 0.5, transform: 'none' }}
        />
        <Skeleton
          variant="text"
          width={[80, 100, 70, 90, 85][index % 5]}
          height={12}
          sx={{ borderRadius: 0.5, transform: 'none', mt: 0.5 }}
        />
      </Box>
      <Skeleton variant="text" width={120} height={14} sx={{ transform: 'none' }} />
      <Skeleton variant="text" width={90} height={14} sx={{ transform: 'none' }} />
      <Box sx={{ display: 'flex', gap: 0.25, justifyContent: 'flex-end' }}>
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
        <Skeleton variant="rounded" width={28} height={28} sx={{ borderRadius: 1.5 }} />
      </Box>
    </Box>
  )
}

function MountCard({
  mount,
  onCopy,
  onUnmount,
  onForceUnmount,
}: {
  mount: Mount
  onCopy: (mount: Mount) => void
  onUnmount: (mount: Mount) => void
  onForceUnmount: (mount: Mount) => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const desktopGridTemplate = 'minmax(0, 1.2fr) minmax(0, 1fr) 180px 100px'

  const parts = mount.source.split('::')
  const archiveName = parts.length > 1 ? parts[1] : parts[0]
  const repoName = parts.length > 1 ? parts[0] : ''

  const iconBtnSx = (color: string) => ({
    width: 28,
    height: 28,
    borderRadius: 1.5,
    color: alpha(color, isDark ? 0.6 : 0.5),
    '&:hover': {
      bgcolor: alpha(color, isDark ? 0.12 : 0.09),
      color: color,
    },
    '&.Mui-disabled': { opacity: 0.28 },
  })

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: desktopGridTemplate,
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 1.125,
        borderBottom: '1px solid',
        borderBottomColor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.04),
        transition: 'all 150ms ease',
        '&:hover': {
          bgcolor: alpha(theme.palette.primary.main, isDark ? 0.04 : 0.03),
        },
        '@media (max-width: 767px)': {
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gridTemplateRows: 'auto auto auto',
          gap: 0.5,
          px: 1.75,
          py: 1.25,
        },
      }}
    >
      {/* Archive name + repo */}
      <Box
        sx={{
          minWidth: 0,
          '@media (max-width: 767px)': {
            gridColumn: 1,
            gridRow: 1,
          },
        }}
      >
        <Box
          title={mount.source}
          sx={{
            fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
            fontSize: '0.78rem',
            fontWeight: 600,
            color: 'text.primary',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {archiveName}
        </Box>
        {repoName && (
          <Box
            component="span"
            sx={{
              fontSize: '0.68rem',
              color: 'text.secondary',
              opacity: 0.7,
              display: 'block',
              mt: 0.25,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {repoName}
          </Box>
        )}
      </Box>

      {/* Mount point */}
      <Box
        sx={{
          display: 'contents',
          '@media (max-width: 767px)': {
            display: 'flex',
            alignItems: 'center',
            gap: 0.75,
            gridColumn: 1,
            gridRow: 2,
            minWidth: 0,
          },
        }}
      >
        <Box
          component="span"
          title={mount.mount_point}
          sx={{
            fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
            fontSize: '0.72rem',
            color: 'text.secondary',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            minWidth: 0,
          }}
        >
          {mount.mount_point}
        </Box>

        {/* Mounted date */}
        <Box
          component="span"
          sx={{
            fontSize: '0.72rem',
            color: 'text.secondary',
            whiteSpace: 'nowrap',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {formatDate(mount.created_at)}
        </Box>
      </Box>

      {/* Actions */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          minWidth: 0,
          justifyContent: 'flex-end',
          '@media (max-width: 767px)': {
            gridColumn: 2,
            gridRow: '1 / 4',
            alignSelf: 'center',
          },
        }}
      >
        <Tooltip title={t('mounts.actions.copyAccessCommand')} arrow>
          <IconButton
            size="small"
            onClick={() => onCopy(mount)}
            aria-label={t('mounts.actions.copyAccessCommand')}
            sx={iconBtnSx(theme.palette.primary.main)}
          >
            <Copy size={15} />
          </IconButton>
        </Tooltip>

        <Tooltip title={t('mounts.actions.unmountArchive')} arrow>
          <IconButton
            size="small"
            onClick={() => onUnmount(mount)}
            aria-label={t('mounts.actions.unmountArchive')}
            sx={iconBtnSx(theme.palette.warning.main)}
          >
            <Trash2 size={15} />
          </IconButton>
        </Tooltip>

        <Tooltip title={t('mounts.actions.forceUnmountTooltip')} arrow>
          <IconButton
            size="small"
            onClick={() => onForceUnmount(mount)}
            aria-label={t('mounts.actions.forceUnmountTooltip')}
            sx={iconBtnSx(theme.palette.error.main)}
          >
            <XCircle size={15} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  )
}

export default function MountsManagementTab() {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const queryClient = useQueryClient()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageMounts = hasGlobalPermission('settings.mounts.manage')

  // Fetch active mounts
  const { data: mountsData, isLoading } = useQuery({
    queryKey: ['mounts'],
    queryFn: async () => {
      const response = await mountsAPI.listMounts()
      return response.data
    },
    enabled: canManageMounts,
    refetchInterval: 10000,
  })

  // Unmount mutation
  const unmountMutation = useMutation({
    mutationFn: ({ mountId, force }: { mountId: string; force: boolean }) =>
      mountsAPI.unmountBorgArchive(mountId, force),
    onSuccess: () => {
      toast.success(t('mountsManagement.unmountedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['mounts'] })
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('mountsManagement.failedToUnmount')
      )
    },
  })

  const mounts: Mount[] = mountsData || []

  const handleUnmount = (mountId: string, force: boolean = false) => {
    track(EventCategory.MOUNT, force ? EventAction.DELETE : EventAction.UNMOUNT, {
      operation: force ? 'force_unmount' : 'unmount',
    })
    unmountMutation.mutate({ mountId, force })
  }

  const copyToClipboard = (mount: Mount) => {
    const containerName = 'borg-web-ui'
    const command = `docker exec -it ${containerName} bash -c "cd ${mount.mount_point} && bash"`
    navigator.clipboard.writeText(command)
    toast.success(t('mounts.copiedToClipboard', { label: t('mounts.actions.accessCommand') }))
    track(EventCategory.MOUNT, EventAction.VIEW, { operation: 'copy_access_command' })
  }

  const desktopGridTemplate = 'minmax(0, 1.2fr) minmax(0, 1fr) 180px 100px'

  if (!canManageMounts) {
    return null
  }

  const tableHeader = (
    <Box
      sx={{
        display: { xs: 'none', md: 'grid' },
        gridTemplateColumns: desktopGridTemplate,
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 1,
        bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.02),
        borderBottom: '1px solid',
        borderBottomColor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
        fontSize: '0.65rem',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'text.disabled',
      }}
    >
      <span>{t('mounts.columns.archive')}</span>
      <span>{t('mounts.columns.mountLocation')}</span>
      <span>{t('mounts.columns.mounted')}</span>
      <Box sx={{ textAlign: 'right' }}>{t('archivesList.columnActions', 'Actions')}</Box>
    </Box>
  )

  // Loading state — real header + table header with skeleton rows
  if (isLoading) {
    return (
      <Box>
        {/* Real header bar */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: { xs: 1.5, sm: 1 },
            px: 2,
            py: 1.25,
            mb: 2.5,
            borderRadius: 2,
            bgcolor: isDark
              ? alpha(theme.palette.info.main, 0.1)
              : alpha(theme.palette.info.main, 0.06),
            border: '1px solid',
            borderColor: isDark
              ? alpha(theme.palette.info.main, 0.2)
              : alpha(theme.palette.info.main, 0.15),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexShrink: 0 }}>
            <HardDrive size={16} style={{ opacity: 0.7 }} />
            <Typography variant="h6" fontWeight={700} sx={{ fontSize: '0.95rem' }}>
              {t('mountsManagement.title')}
            </Typography>
            <Skeleton variant="rounded" width={22} height={20} sx={{ borderRadius: 1 }} />
          </Box>
        </Box>
        {/* Table with real header + skeleton rows */}
        <Box
          sx={{
            borderRadius: 3,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
            overflow: 'hidden',
          }}
        >
          {tableHeader}
          {[0, 1, 2, 3, 4].map((i) => (
            <MountCardSkeleton key={i} index={i} />
          ))}
        </Box>
      </Box>
    )
  }

  return (
    <Box>
      {/* Panel header: title + count + info hint */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          gap: { xs: 1.5, sm: 1 },
          px: 2,
          py: 1.25,
          mb: 2.5,
          borderRadius: 2,
          bgcolor: isDark
            ? alpha(theme.palette.info.main, 0.1)
            : alpha(theme.palette.info.main, 0.06),
          border: '1px solid',
          borderColor: isDark
            ? alpha(theme.palette.info.main, 0.2)
            : alpha(theme.palette.info.main, 0.15),
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexShrink: 0 }}>
          <HardDrive size={16} style={{ opacity: 0.7 }} />
          <Typography variant="h6" fontWeight={700} sx={{ fontSize: '0.95rem' }}>
            {t('mountsManagement.title')}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              fontSize: '0.72rem',
              fontWeight: 600,
              px: 0.75,
              py: 0.2,
              borderRadius: 1,
              bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.06),
              color: 'text.secondary',
              lineHeight: 1.6,
            }}
          >
            {mounts.length}
          </Typography>
        </Box>

        {/* Info tooltip */}
        <Tooltip title={t('mounts.infoAlert')} arrow placement="bottom-end">
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              color: 'text.secondary',
              opacity: 0.6,
              cursor: 'help',
              '&:hover': { opacity: 1 },
              transition: 'opacity 150ms ease',
            }}
          >
            <Info size={15} />
          </Box>
        </Tooltip>
      </Box>

      {/* Empty state */}
      {mounts.length === 0 ? (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
            py: 8,
            color: 'text.secondary',
          }}
        >
          <FolderOpen size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
          <Typography variant="body1" color="text.secondary" fontWeight={500}>
            {t('mountsManagement.empty')}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.75, opacity: 0.7, maxWidth: 360 }}
          >
            {t('mounts.emptyDescription')}
          </Typography>
        </Box>
      ) : (
        <Box
          sx={{
            borderRadius: 3,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
            overflow: 'hidden',
          }}
        >
          {tableHeader}

          {/* Mount rows */}
          {mounts.map((mount) => (
            <MountCard
              key={mount.mount_id}
              mount={mount}
              onCopy={copyToClipboard}
              onUnmount={(m) => handleUnmount(m.mount_id, false)}
              onForceUnmount={(m) => handleUnmount(m.mount_id, true)}
            />
          ))}
        </Box>
      )}
    </Box>
  )
}
