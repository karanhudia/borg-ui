import type { PlanContentFeature, PlanContentManifest } from '../types/planContent'
import { BASE_PATH } from '../utils/basePath'
import planContentManifestData from '../data/plan-content.json'
import localPlanContentUrl from '../data/plan-content.json?url'

const MAX_SUPPORTED_VERSION = 1

export const LOCAL_PLAN_CONTENT_URL =
  BASE_PATH === '/' ? localPlanContentUrl : `${BASE_PATH}${localPlanContentUrl}`
const DEFAULT_REMOTE_PLAN_CONTENT_URL = 'https://updates.borgui.com/plan-content.json'

export const DEFAULT_PLAN_CONTENT_MANIFEST = planContentManifestData as PlanContentManifest

export function getPlanContentUrl() {
  const configuredUrl = import.meta.env.VITE_PLAN_CONTENT_URL?.trim()
  if (configuredUrl) return configuredUrl

  return LOCAL_PLAN_CONTENT_URL
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isLocalizedStringMap(value: unknown): value is Record<string, string> | undefined {
  return (
    value === undefined ||
    (typeof value === 'object' && value !== null && Object.values(value).every(isNonEmptyString))
  )
}

function isValidPlanContentFeature(feature: unknown): feature is PlanContentFeature {
  if (!feature || typeof feature !== 'object') return false

  const candidate = feature as Partial<PlanContentFeature>
  const hasVersionTarget = isNonEmptyString(candidate.available_in)
  const hasAvailability = candidate.availability !== undefined

  return (
    isNonEmptyString(candidate.id) &&
    (candidate.plan === 'community' ||
      candidate.plan === 'pro' ||
      candidate.plan === 'enterprise') &&
    isNonEmptyString(candidate.label) &&
    isLocalizedStringMap(candidate.label_localized) &&
    isNonEmptyString(candidate.description) &&
    isLocalizedStringMap(candidate.description_localized) &&
    (!hasAvailability ||
      candidate.availability === 'included' ||
      candidate.availability === 'coming_soon') &&
    (!hasVersionTarget || !hasAvailability) &&
    (!hasVersionTarget || candidate.availability !== 'included') &&
    (candidate.available_in === undefined || hasVersionTarget)
  )
}

export async function fetchPlanContentManifest(url = getPlanContentUrl()) {
  const configuredUrl = import.meta.env.VITE_PLAN_CONTENT_URL?.trim()
  const candidateUrls =
    configuredUrl || import.meta.env.DEV ? [url] : [DEFAULT_REMOTE_PLAN_CONTENT_URL, url]

  let lastStatus: number | null = null

  for (const candidateUrl of candidateUrls) {
    let response: Response
    try {
      response = await fetch(candidateUrl, {
        headers: {
          Accept: 'application/json',
        },
      })
    } catch {
      continue
    }

    if (!response.ok) {
      lastStatus = response.status
      continue
    }

    const data = (await response.json()) as Partial<PlanContentManifest>
    const version =
      typeof data.version === 'number' ? data.version : DEFAULT_PLAN_CONTENT_MANIFEST.version
    if (version > MAX_SUPPORTED_VERSION) {
      lastStatus = null
      continue
    }
    return {
      version,
      generated_at: data.generated_at,
      features: Array.isArray(data.features)
        ? data.features.filter(isValidPlanContentFeature)
        : DEFAULT_PLAN_CONTENT_MANIFEST.features,
    } satisfies PlanContentManifest
  }

  throw new Error(`Failed to fetch plan content manifest${lastStatus ? ` (${lastStatus})` : ''}`)
}
