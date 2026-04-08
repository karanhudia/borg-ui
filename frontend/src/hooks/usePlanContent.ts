import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  DEFAULT_PLAN_CONTENT_MANIFEST,
  fetchPlanContentManifest,
  getPlanContentUrl,
} from '../services/planContent'
import type { PlanContentFeature } from '../types/planContent'

function getLocaleCandidates(locale?: string): string[] {
  if (!locale) return ['default']

  const trimmed = locale.trim()
  if (!trimmed) return ['default']

  const baseLanguage = trimmed.split('-')[0]
  return Array.from(new Set([trimmed, baseLanguage, 'default']))
}

function resolveLocalizedString(
  fallback: string,
  localized: Record<string, string> | undefined,
  locale?: string
) {
  if (!localized) return fallback

  for (const candidate of getLocaleCandidates(locale)) {
    const value = localized[candidate]
    if (typeof value === 'string' && value.trim().length > 0) return value
  }

  return fallback
}

function resolveFeatureLocale(feature: PlanContentFeature, locale?: string): PlanContentFeature {
  return {
    ...feature,
    label: resolveLocalizedString(feature.label, feature.label_localized, locale),
    description: resolveLocalizedString(feature.description, feature.description_localized, locale),
  }
}

export function usePlanContent() {
  const { i18n } = useTranslation()
  const planContentUrl = getPlanContentUrl()

  const { data, isLoading } = useQuery({
    queryKey: ['plan-content-manifest', planContentUrl],
    queryFn: () => fetchPlanContentManifest(planContentUrl),
    initialData: DEFAULT_PLAN_CONTENT_MANIFEST,
    initialDataUpdatedAt: 0,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const localizedFeatures = useMemo(
    () => data.features.map((feature) => resolveFeatureLocale(feature, i18n.resolvedLanguage)),
    [data.features, i18n.resolvedLanguage]
  )

  return {
    features: localizedFeatures,
    isLoading,
  }
}
