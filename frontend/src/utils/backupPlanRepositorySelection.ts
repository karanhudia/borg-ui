export const applyRepositorySelectionLimit = (
  ids: number[],
  canUseMultiRepository: boolean
): { ids: number[]; limited: boolean } => {
  if (!canUseMultiRepository && ids.length > 1) {
    return { ids: ids.slice(0, 1), limited: true }
  }

  return { ids, limited: false }
}

export const isRepositorySelectionOverLimit = (
  ids: number[],
  canUseMultiRepository: boolean
): boolean => !canUseMultiRepository && ids.length > 1
