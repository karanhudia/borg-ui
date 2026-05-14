import { RepositoriesStep } from './wizard-step/RepositoriesStep'
import { ReviewStep } from './wizard-step/ReviewStep'
import { ScheduleStep } from './wizard-step/ScheduleStep'
import { ScriptsStep } from './wizard-step/ScriptsStep'
import { SettingsStep } from './wizard-step/SettingsStep'
import { SourceStep } from './wizard-step/SourceStep'
import type { BackupPlanWizardStepProps } from './wizard-step/types'

export function BackupPlanWizardStep({
  activeStep,
  stepDefinitions,
  wizardState,
  basicRepositoryState,
  basicRepositoryOpen,
  fullRepositories,
  repositories,
  sshConnections,
  selectedSourceConnection,
  scripts,
  loadingRepositories,
  loadingScripts,
  canUseMultiRepository,
  canUseBorg2,
  repositoryCreatePending,
  updateState,
  updateBasicRepositoryState,
  handleRepositoryIdsChange,
  handlePruneSettingsChange,
  createBasicRepository,
  openSourceExplorer,
  openExcludeExplorer,
  setBasicRepositoryOpen,
  setRepositoryWizardOpen,
  setShowBasicRepositoryPathExplorer,
  t,
}: BackupPlanWizardStepProps) {
  const stepKey = stepDefinitions[activeStep]?.key

  if (stepKey === 'source') {
    return (
      <SourceStep
        wizardState={wizardState}
        sshConnections={sshConnections}
        updateState={updateState}
        openSourceExplorer={openSourceExplorer}
        openExcludeExplorer={openExcludeExplorer}
        t={t}
      />
    )
  }

  if (stepKey === 'repositories') {
    return (
      <RepositoriesStep
        wizardState={wizardState}
        basicRepositoryState={basicRepositoryState}
        basicRepositoryOpen={basicRepositoryOpen}
        fullRepositories={fullRepositories}
        loadingRepositories={loadingRepositories}
        canUseMultiRepository={canUseMultiRepository}
        canUseBorg2={canUseBorg2}
        repositoryCreatePending={repositoryCreatePending}
        updateBasicRepositoryState={updateBasicRepositoryState}
        handleRepositoryIdsChange={handleRepositoryIdsChange}
        createBasicRepository={createBasicRepository}
        setBasicRepositoryOpen={setBasicRepositoryOpen}
        setRepositoryWizardOpen={setRepositoryWizardOpen}
        setShowBasicRepositoryPathExplorer={setShowBasicRepositoryPathExplorer}
        t={t}
      />
    )
  }

  if (stepKey === 'settings') {
    return (
      <SettingsStep
        wizardState={wizardState}
        canUseMultiRepository={canUseMultiRepository}
        updateState={updateState}
        t={t}
      />
    )
  }

  if (stepKey === 'scripts') {
    return (
      <ScriptsStep
        wizardState={wizardState}
        scripts={scripts}
        loadingScripts={loadingScripts}
        updateState={updateState}
        t={t}
      />
    )
  }

  if (stepKey === 'schedule') {
    return (
      <ScheduleStep
        wizardState={wizardState}
        updateState={updateState}
        handlePruneSettingsChange={handlePruneSettingsChange}
        t={t}
      />
    )
  }

  return (
    <ReviewStep
      wizardState={wizardState}
      repositories={repositories}
      selectedSourceConnection={selectedSourceConnection}
      scripts={scripts}
      t={t}
    />
  )
}
