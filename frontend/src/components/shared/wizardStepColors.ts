export const wizardStepColors = {
  // RepositoryWizard colors
  location: { light: '#1565c0', dark: '#64b5f6' },
  source: { light: '#2e7d32', dark: '#81c784' },
  security: { light: '#7b1fa2', dark: '#ce93d8' },
  config: { light: '#e65100', dark: '#ffb74d' },
  review: { light: '#0277bd', dark: '#4fc3f7' },

  // ScheduleWizard colors (same palette, different mapping)
  basic: { light: '#1565c0', dark: '#64b5f6' },
  schedule: { light: '#e65100', dark: '#ffb74d' },
  scripts: { light: '#7b1fa2', dark: '#ce93d8' },
  maintenance: { light: '#2e7d32', dark: '#81c784' },
} as const

export type WizardStepColorKey = keyof typeof wizardStepColors
export type WizardStepColorMode = keyof (typeof wizardStepColors)['location']

export function getWizardStepColor(stepKey: string, mode: WizardStepColorMode) {
  const colors = wizardStepColors[stepKey as WizardStepColorKey] ?? wizardStepColors.location
  return colors[mode]
}
