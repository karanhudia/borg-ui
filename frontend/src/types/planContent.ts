import type { Plan } from '../core/features'

export type PlanContentLocalizedText = Record<string, string>

export interface PlanContentFeature {
  id: string
  plan: Plan
  label: string
  label_localized?: PlanContentLocalizedText
  description: string
  description_localized?: PlanContentLocalizedText
  available_in?: string
}

export interface PlanContentManifest {
  version: number
  generated_at?: string
  features: PlanContentFeature[]
}
