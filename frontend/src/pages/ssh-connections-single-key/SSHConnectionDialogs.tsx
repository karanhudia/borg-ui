import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import { DeleteConnectionDialog } from './dialogs/DeleteConnectionDialog'
import { DeleteKeyDialog } from './dialogs/DeleteKeyDialog'
import { DeployKeyDialog } from './dialogs/DeployKeyDialog'
import { EditConnectionDialog } from './dialogs/EditConnectionDialog'
import { GenerateKeyDialog } from './dialogs/GenerateKeyDialog'
import { ImportKeyDialog } from './dialogs/ImportKeyDialog'
import { RedeployKeyDialog } from './dialogs/RedeployKeyDialog'
import { TestConnectionDialog } from './dialogs/TestConnectionDialog'
import type {
  DeployConnectionPayload,
  ImportKeyPayload,
  SSHConnection,
  SystemSSHKey,
  TestConnectionPayload,
  UpdateConnectionPayload,
} from './types'

interface SSHConnectionDialogsProps {
  t: TFunction
  systemKey: SystemSSHKey | undefined
  connections: SSHConnection[]
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
  handleDeployKey: () => void
  handleTestManualConnection: () => void
  handleUpdateConnection: () => void
  confirmDeleteConnection: () => void
  handleConfirmRedeployKey: () => void
  handleDeleteKey: () => void
}

export function SSHConnectionDialogs({
  t,
  systemKey,
  connections,
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
  handleDeployKey,
  handleTestManualConnection,
  handleUpdateConnection,
  confirmDeleteConnection,
  handleConfirmRedeployKey,
  handleDeleteKey,
}: SSHConnectionDialogsProps) {
  return (
    <>
      <GenerateKeyDialog
        t={t}
        open={generateDialogOpen}
        setOpen={setGenerateDialogOpen}
        keyType={keyType}
        setKeyType={setKeyType}
        pending={generateKeyPending}
        onGenerate={handleGenerateKey}
      />
      <ImportKeyDialog
        t={t}
        open={importDialogOpen}
        setOpen={setImportDialogOpen}
        importForm={importForm}
        setImportForm={setImportForm}
        pending={importKeyPending}
        onImport={handleImportKey}
      />
      <DeployKeyDialog
        t={t}
        open={deployDialogOpen}
        setOpen={setDeployDialogOpen}
        connectionForm={connectionForm}
        setConnectionForm={setConnectionForm}
        pending={deployKeyPending}
        onDeploy={handleDeployKey}
      />
      <TestConnectionDialog
        t={t}
        open={testConnectionDialogOpen}
        setOpen={setTestConnectionDialogOpen}
        testConnectionForm={testConnectionForm}
        setTestConnectionForm={setTestConnectionForm}
        pending={testConnectionPending}
        onTest={handleTestManualConnection}
      />
      <EditConnectionDialog
        t={t}
        open={editConnectionDialogOpen}
        setOpen={setEditConnectionDialogOpen}
        setSelectedConnection={setSelectedConnection}
        editConnectionForm={editConnectionForm}
        setEditConnectionForm={setEditConnectionForm}
        pending={updateConnectionPending}
        onUpdate={handleUpdateConnection}
      />
      <DeleteConnectionDialog
        t={t}
        open={deleteConnectionDialogOpen}
        setOpen={setDeleteConnectionDialogOpen}
        selectedConnection={selectedConnection}
        setSelectedConnection={setSelectedConnection}
        pending={deleteConnectionPending}
        onConfirmDelete={confirmDeleteConnection}
      />
      <RedeployKeyDialog
        t={t}
        open={redeployKeyDialogOpen}
        setOpen={setRedeployKeyDialogOpen}
        selectedConnection={selectedConnection}
        setSelectedConnection={setSelectedConnection}
        redeployPassword={redeployPassword}
        setRedeployPassword={setRedeployPassword}
        pending={redeployKeyPending}
        onConfirmRedeploy={handleConfirmRedeployKey}
      />
      <DeleteKeyDialog
        t={t}
        open={deleteKeyDialogOpen}
        setOpen={setDeleteKeyDialogOpen}
        systemKey={systemKey}
        connections={connections}
        pending={deleteKeyPending}
        onDelete={handleDeleteKey}
      />
    </>
  )
}
