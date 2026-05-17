import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'

import type { PruneSettings } from '../../../components/PruneSettingsInput'
import type { Repository } from '../../../types'
import type { BasicRepositoryState, ScriptOption, SSHConnection, WizardState } from '../types'

export interface BackupPlanWizardStepProps {
  activeStep: number
  stepDefinitions: Array<{ key: string }>
  wizardState: WizardState
  basicRepositoryState: BasicRepositoryState
  basicRepositoryOpen: boolean
  fullRepositories: Repository[]
  repositories: Repository[]
  sshConnections: SSHConnection[]
  selectedSourceConnection: SSHConnection | null
  scripts: ScriptOption[]
  loadingRepositories: boolean
  loadingScripts: boolean
  canUseMultiRepository: boolean
  canUseBorg2: boolean
  repositoryCreatePending: boolean
  updateState: (updates: Partial<WizardState>) => void
  onCreateScript: (input: SourceScriptCreateInput) => Promise<{ id: number }>
  updateBasicRepositoryState: (updates: Partial<BasicRepositoryState>) => void
  handleRepositoryIdsChange: (ids: number[]) => void
  handlePruneSettingsChange: (values: PruneSettings) => void
  createBasicRepository: () => void
  openSourceExplorer: () => void
  openExcludeExplorer: () => void
  setBasicRepositoryOpen: Dispatch<SetStateAction<boolean>>
  setRepositoryWizardOpen: Dispatch<SetStateAction<boolean>>
  setShowBasicRepositoryPathExplorer: Dispatch<SetStateAction<boolean>>
  t: TFunction
}

export interface SourceScriptCreateInput {
  name: string
  description: string
  content: string
  timeout: number
  run_on: string
  category: string
}
