import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_PLAN_CONTENT_MANIFEST,
  fetchPlanContentManifest,
  mergePlanContentFeatures,
} from './planContent'
import type { PlanContentFeature } from '../types/planContent'

describe('planContent', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('merges bundled feature copy into a stale hosted manifest', async () => {
    const staleRemoteFeatures = DEFAULT_PLAN_CONTENT_MANIFEST.features.filter(
      (feature) => !['backup_plan_mixed_sources', 'rclone', 'managed_agents'].includes(feature.id)
    )

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          version: 1,
          generated_at: '2026-05-16T00:00:00Z',
          features: staleRemoteFeatures,
        }),
      })
    )

    const manifest = await fetchPlanContentManifest('/plan-content.json')
    const featureIds = manifest.features.map((feature) => feature.id)

    expect(featureIds).toContain('backup_plan_mixed_sources')
    expect(featureIds).toContain('rclone')
    expect(featureIds).toContain('managed_agents')
  })

  it('keeps hosted copy when a feature exists in both manifests', () => {
    const hostedFeature: PlanContentFeature = {
      id: 'rclone',
      plan: 'pro',
      label: 'Hosted rclone label',
      description: 'Hosted rclone description.',
      availability: 'included',
    }

    const mergedFeatures = mergePlanContentFeatures([hostedFeature])
    const rcloneFeatures = mergedFeatures.filter((feature) => feature.id === 'rclone')

    expect(rcloneFeatures).toHaveLength(1)
    expect(rcloneFeatures[0].label).toBe('Hosted rclone label')
  })
})
