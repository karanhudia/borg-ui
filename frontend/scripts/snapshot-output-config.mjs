import path from 'node:path'

export function resolveSnapshotOutputDir(frontendRoot, env = process.env) {
  const configuredDir = env.STORYBOOK_SNAPSHOTS_DIR

  if (!configuredDir) {
    return path.join(frontendRoot, 'visual-screenshots')
  }

  return path.isAbsolute(configuredDir) ? configuredDir : path.resolve(frontendRoot, configuredDir)
}
