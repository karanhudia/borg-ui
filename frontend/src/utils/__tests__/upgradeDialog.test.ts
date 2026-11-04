import { beforeEach, describe, expect, it } from 'vitest'
import {
  closeUpgradeDialog,
  isAnsweredRefusal,
  openUpgradeForRefusal,
  upgradeDialogStore,
} from '../upgradeDialog'

const refusal = (method: string, detail: unknown) => ({
  config: { method },
  response: { status: 403, data: { detail } },
})

const borgV2 = {
  key: 'backend.errors.plan.featureNotAvailable',
  feature: 'borg_v2',
  required: 'pro',
  current: 'community',
}

describe('openUpgradeForRefusal', () => {
  beforeEach(() => closeUpgradeDialog())

  it('opens the card for an action the plan refused', () => {
    openUpgradeForRefusal(refusal('post', borgV2))
    expect(upgradeDialogStore.get()).toEqual({ feature: 'borg_v2', surface: 'api', refused: true })
  })

  it('reads a detail sent as a JSON string', () => {
    openUpgradeForRefusal(refusal('post', JSON.stringify(borgV2)))
    expect(upgradeDialogStore.get()?.feature).toBe('borg_v2')
  })

  it('leaves reads alone: a page loading never pops a dialog', () => {
    openUpgradeForRefusal(refusal('get', borgV2))
    expect(upgradeDialogStore.get()).toBeNull()
  })

  it('ignores other errors and unknown features', () => {
    openUpgradeForRefusal(refusal('post', { key: 'backend.errors.repo.notFound' }))
    openUpgradeForRefusal(refusal('post', { ...borgV2, feature: 'no_such_feature' }))
    openUpgradeForRefusal(new Error('network'))
    expect(upgradeDialogStore.get()).toBeNull()
  })

  it('lets the caller keep its message for a plan error the dialog cannot answer', () => {
    expect(isAnsweredRefusal(refusal('post', borgV2))).toBe(true)
    expect(isAnsweredRefusal(refusal('post', { ...borgV2, feature: 'no_such_feature' }))).toBe(
      false
    )
    expect(isAnsweredRefusal(refusal('post', { key: borgV2.key }))).toBe(false)
  })
})
