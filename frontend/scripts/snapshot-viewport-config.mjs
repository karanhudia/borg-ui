export const snapshotViewports = [
  {
    id: 'desktop',
    width: 1280,
    height: 800,
    fileSuffix: '',
  },
  {
    id: 'mobile',
    width: 390,
    height: 844,
    fileSuffix: '--mobile',
  },
]

export function snapshotFileName(storyId, viewport) {
  return `${storyId}${viewport.fileSuffix}.png`
}
