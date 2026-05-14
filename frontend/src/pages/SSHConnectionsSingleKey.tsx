import { useState, useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTheme } from '@mui/material'
import { toast } from 'react-hot-toast'
import { sshKeysAPI } from '../services/api'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { SSHConnectionsSingleKeyView } from './ssh-connections-single-key/SSHConnectionsSingleKeyView'
import {
  createConnectionForm,
  createEditConnectionForm,
  createImportForm,
  createTestConnectionForm,
} from './ssh-connections-single-key/formDefaults'
import type {
  DeployConnectionPayload,
  ImportKeyPayload,
  SSHConnection,
  TestConnectionPayload,
  UpdateConnectionPayload,
} from './ssh-connections-single-key/types'

export default function SSHConnectionsSingleKey() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageSsh = hasGlobalPermission('settings.ssh.manage')
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  // State
  const [keyVisible, setKeyVisible] = useState(false)
  const [fingerprintVisible, setFingerprintVisible] = useState(false)
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false)
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [deployDialogOpen, setDeployDialogOpen] = useState(false)
  const [testConnectionDialogOpen, setTestConnectionDialogOpen] = useState(false)
  const [editConnectionDialogOpen, setEditConnectionDialogOpen] = useState(false)
  const [deleteConnectionDialogOpen, setDeleteConnectionDialogOpen] = useState(false)
  const [deleteKeyDialogOpen, setDeleteKeyDialogOpen] = useState(false)
  const [redeployKeyDialogOpen, setRedeployKeyDialogOpen] = useState(false)
  const [selectedConnection, setSelectedConnection] = useState<SSHConnection | null>(null)
  const [keyType, setKeyType] = useState('ed25519')
  const [redeployPassword, setRedeployPassword] = useState('')
  const [importForm, setImportForm] = useState(createImportForm)
  const [connectionForm, setConnectionForm] = useState(createConnectionForm)
  const [testConnectionForm, setTestConnectionForm] = useState(createTestConnectionForm)
  const [editConnectionForm, setEditConnectionForm] = useState(createEditConnectionForm)

  // Queries
  const { data: systemKeyData, isLoading: keyLoading } = useQuery({
    queryKey: ['system-ssh-key'],
    queryFn: sshKeysAPI.getSystemKey,
    enabled: canManageSsh,
    refetchInterval: 30000,
  })

  const { data: connectionsData, isLoading: connectionsLoading } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
    enabled: canManageSsh,
    refetchInterval: 30000,
  })

  const systemKey = systemKeyData?.data?.ssh_key
  const keyExists = systemKeyData?.data?.exists
  const connections: SSHConnection[] = connectionsData?.data?.connections || []

  // Statistics
  const stats = {
    totalConnections: connections.length,
    activeConnections: connections.filter((c) => c.status === 'connected').length,
    failedConnections: connections.filter((c) => c.status === 'failed').length,
  }

  // Mutations
  const generateKeyMutation = useMutation({
    mutationFn: (data: { name: string; key_type: string; description?: string }) =>
      sshKeysAPI.generateSSHKey(data),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyGenerated'))
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      setGenerateDialogOpen(false)
      track(EventCategory.SSH, EventAction.CREATE, { resource: 'key' })
    },
    onError: (error: unknown) => {
      console.error('Failed to generate SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.toasts.keyGenerateFailed')
      )
    },
  })

  const importKeyMutation = useMutation({
    mutationFn: (data: ImportKeyPayload) => sshKeysAPI.importSSHKey(data),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyImported'))
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      setImportDialogOpen(false)
      setImportForm(createImportForm())
      track(EventCategory.SSH, EventAction.UPLOAD, { resource: 'key' })
    },
    onError: (error: unknown) => {
      console.error('Failed to import SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('sshConnections.toasts.keyImportFailed')
      )
    },
  })

  const deployKeyMutation = useMutation({
    mutationFn: (data: { keyId: number; connectionData: DeployConnectionPayload }) =>
      sshKeysAPI.deploySSHKey(data.keyId, data.connectionData),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyDeployed'))
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeployDialogOpen(false)
      setConnectionForm(createConnectionForm())
      track(EventCategory.SSH, EventAction.CREATE, { resource: 'connection' })
    },
    onError: (error: unknown) => {
      console.error('Failed to deploy SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('sshConnections.toasts.keyDeployFailed')
      )
    },
  })

  const testConnectionMutation = useMutation({
    mutationFn: (data: { keyId: number; connectionData: TestConnectionPayload }) =>
      sshKeysAPI.testSSHConnection(data.keyId, data.connectionData),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('sshConnections.toasts.connectionTestSuccess'))
        track(EventCategory.SSH, EventAction.TEST, { resource: 'connection' })
      } else {
        toast.error(t('sshConnections.toasts.connectionTestFailed'))
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
    },
    onError: (error: unknown) => {
      console.error('Failed to test connection:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.toasts.connectionTestFailed')
      )
    },
  })

  const updateConnectionMutation = useMutation({
    mutationFn: (data: { connectionId: number; connectionData: UpdateConnectionPayload }) =>
      sshKeysAPI.updateSSHConnection(data.connectionId, data.connectionData),
    onSuccess: async (_response, variables) => {
      toast.success(t('sshConnections.toasts.connectionUpdated'))
      setEditConnectionDialogOpen(false)
      setSelectedConnection(null)
      track(EventCategory.SSH, EventAction.EDIT, { resource: 'connection' })

      // Automatically test the connection after update
      try {
        await sshKeysAPI.testExistingConnection(variables.connectionId)
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      } catch (error: unknown) {
        // Test failure is already shown in the connection status
        console.error('Failed to test connection:', error)
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      }
    },
    onError: (error: unknown) => {
      console.error('Failed to update connection:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.toasts.connectionUpdateFailed')
      )
    },
  })

  const deleteConnectionMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.deleteSSHConnection(connectionId),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.connectionDeleted'))
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeleteConnectionDialogOpen(false)
      setSelectedConnection(null)
      track(EventCategory.SSH, EventAction.DELETE, { resource: 'connection' })
    },
    onError: (error: unknown) => {
      console.error('Failed to delete connection:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.toasts.connectionDeleteFailed')
      )
    },
  })

  const refreshStorageMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.refreshConnectionStorage(connectionId),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.storageRefreshed'))
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      track(EventCategory.SSH, EventAction.VIEW, { resource: 'storage' })
    },
    onError: (error: unknown) => {
      console.error('Failed to refresh storage:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.toasts.storageRefreshFailed')
      )
    },
  })

  const testExistingConnectionMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.testExistingConnection(connectionId),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('sshConnections.toasts.connectionTestSuccess'))
      } else {
        toast.error(
          translateBackendKey(response.data.error) ||
            t('sshConnections.toasts.connectionTestFailed')
        )
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      track(EventCategory.SSH, EventAction.TEST, { resource: 'connection' })
    },
    onError: (error: unknown) => {
      console.error('Failed to test connection:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.toasts.connectionTestFailed')
      )
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: number) => sshKeysAPI.deleteSSHKey(keyId),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyDeleted'))
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeleteKeyDialogOpen(false)
      track(EventCategory.SSH, EventAction.DELETE, { resource: 'key' })
    },
    onError: (error: unknown) => {
      console.error('Failed to delete SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('sshConnections.toasts.keyDeleteFailed')
      )
    },
  })

  const redeployKeyMutation = useMutation({
    mutationFn: ({ connectionId, password }: { connectionId: number; password: string }) =>
      sshKeysAPI.redeployKeyToConnection(connectionId, password),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('sshConnections.toasts.keyDeployed'))
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
        setRedeployKeyDialogOpen(false)
        setRedeployPassword('')
        track(EventCategory.SSH, EventAction.START, {
          resource: 'connection',
          operation: 'deploy_key',
        })
      } else {
        toast.error(
          translateBackendKey(response.data.error) || t('sshConnections.toasts.keyDeployFailed')
        )
      }
    },
    onError: (error: unknown) => {
      console.error('Failed to redeploy SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('sshConnections.toasts.keyDeployFailed')
      )
    },
  })

  // Auto-refresh storage for connections without storage info
  useEffect(() => {
    if (!canManageSsh) {
      return
    }
    if (connections && connections.length > 0) {
      const connectionsWithoutStorage = connections.filter((conn) => !conn.storage)

      if (connectionsWithoutStorage.length > 0) {
        // Refresh storage for each connection without storage (silently)
        connectionsWithoutStorage.forEach((conn) => {
          sshKeysAPI.refreshConnectionStorage(conn.id).catch(() => {
            // Silently fail - will show "No storage info" in card
          })
        })

        // Invalidate query after delay to show updated data
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
        }, 2000)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connections?.length])

  if (!canManageSsh) {
    return <Navigate to="/dashboard" replace />
  }

  // Handlers
  const handleGenerateKey = () => {
    generateKeyMutation.mutate({
      name: 'System SSH Key',
      key_type: keyType,
      description: 'System SSH key for all remote connections',
    })
  }

  const handleImportKey = () => {
    importKeyMutation.mutate(importForm)
  }

  const handleCopyPublicKey = () => {
    if (systemKey?.public_key) {
      navigator.clipboard.writeText(systemKey.public_key)
      toast.success(t('sshConnections.toasts.publicKeyCopied'))
    }
  }

  const handleDeployKey = () => {
    if (!systemKey) return
    deployKeyMutation.mutate({
      keyId: systemKey.id,
      connectionData: connectionForm,
    })
  }

  const handleTestManualConnection = () => {
    if (!systemKey) return
    testConnectionMutation.mutate({
      keyId: systemKey.id,
      connectionData: testConnectionForm,
    })
    setTestConnectionDialogOpen(false)
    setTestConnectionForm(createTestConnectionForm())
  }

  const handleEditConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setEditConnectionForm({
      host: connection.host,
      username: connection.username,
      port: connection.port,
      use_sftp_mode: connection.use_sftp_mode,
      use_sudo: connection.use_sudo,
      default_path: connection.default_path || '',
      ssh_path_prefix: connection.ssh_path_prefix || '',
      mount_point: connection.mount_point || '',
    })
    setEditConnectionDialogOpen(true)
  }

  const handleUpdateConnection = () => {
    if (!selectedConnection) return
    updateConnectionMutation.mutate({
      connectionId: selectedConnection.id,
      connectionData: editConnectionForm,
    })
  }

  const handleDeleteConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setDeleteConnectionDialogOpen(true)
  }

  const confirmDeleteConnection = () => {
    if (!selectedConnection) return
    deleteConnectionMutation.mutate(selectedConnection.id)
  }

  const handleTestConnection = (connection: SSHConnection) => {
    testExistingConnectionMutation.mutate(connection.id)
  }

  const handleDeployKeyToConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setRedeployKeyDialogOpen(true)
  }

  const handleConfirmRedeployKey = () => {
    if (!selectedConnection || !redeployPassword) return
    redeployKeyMutation.mutate({
      connectionId: selectedConnection.id,
      password: redeployPassword,
    })
  }

  const handleDeleteKey = () => {
    if (!systemKey) return
    deleteKeyMutation.mutate(systemKey.id)
  }

  return (
    <SSHConnectionsSingleKeyView
      t={t}
      theme={theme}
      isDark={isDark}
      keyLoading={keyLoading}
      connectionsLoading={connectionsLoading}
      keyExists={keyExists}
      systemKey={systemKey}
      connections={connections}
      stats={stats}
      canManageSsh={canManageSsh}
      keyVisible={keyVisible}
      setKeyVisible={setKeyVisible}
      fingerprintVisible={fingerprintVisible}
      setFingerprintVisible={setFingerprintVisible}
      generateDialogOpen={generateDialogOpen}
      setGenerateDialogOpen={setGenerateDialogOpen}
      importDialogOpen={importDialogOpen}
      setImportDialogOpen={setImportDialogOpen}
      deployDialogOpen={deployDialogOpen}
      setDeployDialogOpen={setDeployDialogOpen}
      testConnectionDialogOpen={testConnectionDialogOpen}
      setTestConnectionDialogOpen={setTestConnectionDialogOpen}
      editConnectionDialogOpen={editConnectionDialogOpen}
      setEditConnectionDialogOpen={setEditConnectionDialogOpen}
      deleteConnectionDialogOpen={deleteConnectionDialogOpen}
      setDeleteConnectionDialogOpen={setDeleteConnectionDialogOpen}
      deleteKeyDialogOpen={deleteKeyDialogOpen}
      setDeleteKeyDialogOpen={setDeleteKeyDialogOpen}
      redeployKeyDialogOpen={redeployKeyDialogOpen}
      setRedeployKeyDialogOpen={setRedeployKeyDialogOpen}
      selectedConnection={selectedConnection}
      setSelectedConnection={setSelectedConnection}
      keyType={keyType}
      setKeyType={setKeyType}
      redeployPassword={redeployPassword}
      setRedeployPassword={setRedeployPassword}
      importForm={importForm}
      setImportForm={setImportForm}
      connectionForm={connectionForm}
      setConnectionForm={setConnectionForm}
      testConnectionForm={testConnectionForm}
      setTestConnectionForm={setTestConnectionForm}
      editConnectionForm={editConnectionForm}
      setEditConnectionForm={setEditConnectionForm}
      generateKeyPending={generateKeyMutation.isPending}
      importKeyPending={importKeyMutation.isPending}
      deployKeyPending={deployKeyMutation.isPending}
      testConnectionPending={testConnectionMutation.isPending}
      updateConnectionPending={updateConnectionMutation.isPending}
      deleteConnectionPending={deleteConnectionMutation.isPending}
      deleteKeyPending={deleteKeyMutation.isPending}
      redeployKeyPending={redeployKeyMutation.isPending}
      handleGenerateKey={handleGenerateKey}
      handleImportKey={handleImportKey}
      handleCopyPublicKey={handleCopyPublicKey}
      handleDeployKey={handleDeployKey}
      handleTestManualConnection={handleTestManualConnection}
      handleEditConnection={handleEditConnection}
      handleUpdateConnection={handleUpdateConnection}
      handleDeleteConnection={handleDeleteConnection}
      confirmDeleteConnection={confirmDeleteConnection}
      handleTestConnection={handleTestConnection}
      handleDeployKeyToConnection={handleDeployKeyToConnection}
      handleConfirmRedeployKey={handleConfirmRedeployKey}
      handleDeleteKey={handleDeleteKey}
      onRefreshConnections={() => queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })}
      onRefreshStorage={(connectionId) => refreshStorageMutation.mutate(connectionId)}
    />
  )
}
