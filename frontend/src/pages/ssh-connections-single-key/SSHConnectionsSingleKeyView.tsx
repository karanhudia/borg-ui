import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import type { Theme } from '@mui/material/styles'
import { Box } from '@mui/material'
import { SSHConnectionDialogs } from './SSHConnectionDialogs'
import { SSHConnectionsLoadingSkeleton } from './SSHConnectionsLoadingSkeleton'
import { RemoteConnectionsSection } from './view/RemoteConnectionsSection'
import { SSHPageHeader } from './view/SSHPageHeader'
import { SSHStatsBand } from './view/SSHStatsBand'
import { SystemKeyCard } from './view/SystemKeyCard'
import type {
  DeployConnectionPayload,
  ImportKeyPayload,
  SSHConnection,
  SystemSSHKey,
  TestConnectionPayload,
  UpdateConnectionPayload,
} from './types'

interface Stats {
  totalConnections: number
  activeConnections: number
  failedConnections: number
}

interface SSHConnectionsSingleKeyViewProps {
  t: TFunction
  theme: Theme
  isDark: boolean
  keyLoading: boolean
  connectionsLoading: boolean
  keyExists: boolean | undefined
  systemKey: SystemSSHKey | undefined
  connections: SSHConnection[]
  stats: Stats
  canManageSsh: boolean
  keyVisible: boolean
  setKeyVisible: Dispatch<SetStateAction<boolean>>
  fingerprintVisible: boolean
  setFingerprintVisible: Dispatch<SetStateAction<boolean>>
  generateDialogOpen: boolean
  setGenerateDialogOpen: Dispatch<SetStateAction<boolean>>
  importDialogOpen: boolean
  setImportDialogOpen: Dispatch<SetStateAction<boolean>>
  deployDialogOpen: boolean
  setDeployDialogOpen: Dispatch<SetStateAction<boolean>>
  testConnectionDialogOpen: boolean
  setTestConnectionDialogOpen: Dispatch<SetStateAction<boolean>>
  editConnectionDialogOpen: boolean
  setEditConnectionDialogOpen: Dispatch<SetStateAction<boolean>>
  deleteConnectionDialogOpen: boolean
  setDeleteConnectionDialogOpen: Dispatch<SetStateAction<boolean>>
  deleteKeyDialogOpen: boolean
  setDeleteKeyDialogOpen: Dispatch<SetStateAction<boolean>>
  redeployKeyDialogOpen: boolean
  setRedeployKeyDialogOpen: Dispatch<SetStateAction<boolean>>
  selectedConnection: SSHConnection | null
  setSelectedConnection: Dispatch<SetStateAction<SSHConnection | null>>
  keyType: string
  setKeyType: Dispatch<SetStateAction<string>>
  redeployPassword: string
  setRedeployPassword: Dispatch<SetStateAction<string>>
  importForm: ImportKeyPayload
  setImportForm: Dispatch<SetStateAction<ImportKeyPayload>>
  connectionForm: DeployConnectionPayload
  setConnectionForm: Dispatch<SetStateAction<DeployConnectionPayload>>
  testConnectionForm: TestConnectionPayload
  setTestConnectionForm: Dispatch<SetStateAction<TestConnectionPayload>>
  editConnectionForm: UpdateConnectionPayload
  setEditConnectionForm: Dispatch<SetStateAction<UpdateConnectionPayload>>
  generateKeyPending: boolean
  importKeyPending: boolean
  deployKeyPending: boolean
  testConnectionPending: boolean
  updateConnectionPending: boolean
  deleteConnectionPending: boolean
  deleteKeyPending: boolean
  redeployKeyPending: boolean
  handleGenerateKey: () => void
  handleImportKey: () => void
  handleCopyPublicKey: () => void
  handleDeployKey: () => void
  handleTestManualConnection: () => void
  handleEditConnection: (connection: SSHConnection) => void
  handleUpdateConnection: () => void
  handleDeleteConnection: (connection: SSHConnection) => void
  confirmDeleteConnection: () => void
  handleTestConnection: (connection: SSHConnection) => void
  handleDeployKeyToConnection: (connection: SSHConnection) => void
  handleConfirmRedeployKey: () => void
  handleDeleteKey: () => void
  onRefreshConnections: () => void
  onRefreshStorage: (connectionId: number) => void
}

export function SSHConnectionsSingleKeyView({
  t,
  theme,
  isDark,
  keyLoading,
  connectionsLoading,
  keyExists,
  systemKey,
  connections,
  stats,
  canManageSsh,
  keyVisible,
  setKeyVisible,
  fingerprintVisible,
  setFingerprintVisible,
  generateDialogOpen,
  setGenerateDialogOpen,
  importDialogOpen,
  setImportDialogOpen,
  deployDialogOpen,
  setDeployDialogOpen,
  testConnectionDialogOpen,
  setTestConnectionDialogOpen,
  editConnectionDialogOpen,
  setEditConnectionDialogOpen,
  deleteConnectionDialogOpen,
  setDeleteConnectionDialogOpen,
  deleteKeyDialogOpen,
  setDeleteKeyDialogOpen,
  redeployKeyDialogOpen,
  setRedeployKeyDialogOpen,
  selectedConnection,
  setSelectedConnection,
  keyType,
  setKeyType,
  redeployPassword,
  setRedeployPassword,
  importForm,
  setImportForm,
  connectionForm,
  setConnectionForm,
  testConnectionForm,
  setTestConnectionForm,
  editConnectionForm,
  setEditConnectionForm,
  generateKeyPending,
  importKeyPending,
  deployKeyPending,
  testConnectionPending,
  updateConnectionPending,
  deleteConnectionPending,
  deleteKeyPending,
  redeployKeyPending,
  handleGenerateKey,
  handleImportKey,
  handleCopyPublicKey,
  handleDeployKey,
  handleTestManualConnection,
  handleEditConnection,
  handleUpdateConnection,
  handleDeleteConnection,
  confirmDeleteConnection,
  handleTestConnection,
  handleDeployKeyToConnection,
  handleConfirmRedeployKey,
  handleDeleteKey,
  onRefreshConnections,
  onRefreshStorage,
}: SSHConnectionsSingleKeyViewProps) {
  if (keyLoading || connectionsLoading) {
    return <SSHConnectionsLoadingSkeleton isDark={isDark} />
  }

  return (
    <Box>
      <SSHPageHeader t={t} />
      {keyExists && <SSHStatsBand t={t} theme={theme} isDark={isDark} stats={stats} />}
      <SystemKeyCard
        t={t}
        theme={theme}
        isDark={isDark}
        keyExists={keyExists}
        systemKey={systemKey}
        keyVisible={keyVisible}
        setKeyVisible={setKeyVisible}
        fingerprintVisible={fingerprintVisible}
        setFingerprintVisible={setFingerprintVisible}
        setGenerateDialogOpen={setGenerateDialogOpen}
        setImportDialogOpen={setImportDialogOpen}
        setDeployDialogOpen={setDeployDialogOpen}
        setTestConnectionDialogOpen={setTestConnectionDialogOpen}
        setDeleteKeyDialogOpen={setDeleteKeyDialogOpen}
        onCopyPublicKey={handleCopyPublicKey}
      />
      <RemoteConnectionsSection
        t={t}
        theme={theme}
        isDark={isDark}
        keyExists={keyExists}
        connections={connections}
        canManageSsh={canManageSsh}
        onRefreshConnections={onRefreshConnections}
        onEditConnection={handleEditConnection}
        onDeleteConnection={handleDeleteConnection}
        onRefreshStorage={onRefreshStorage}
        onTestConnection={handleTestConnection}
        onDeployKeyToConnection={handleDeployKeyToConnection}
      />
      <SSHConnectionDialogs
        t={t}
        systemKey={systemKey}
        connections={connections}
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
        generateKeyPending={generateKeyPending}
        importKeyPending={importKeyPending}
        deployKeyPending={deployKeyPending}
        testConnectionPending={testConnectionPending}
        updateConnectionPending={updateConnectionPending}
        deleteConnectionPending={deleteConnectionPending}
        deleteKeyPending={deleteKeyPending}
        redeployKeyPending={redeployKeyPending}
        handleGenerateKey={handleGenerateKey}
        handleImportKey={handleImportKey}
        handleDeployKey={handleDeployKey}
        handleTestManualConnection={handleTestManualConnection}
        handleUpdateConnection={handleUpdateConnection}
        confirmDeleteConnection={confirmDeleteConnection}
        handleConfirmRedeployKey={handleConfirmRedeployKey}
        handleDeleteKey={handleDeleteKey}
      />
    </Box>
  )
}
