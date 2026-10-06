export type BorgBinary = Record<string, unknown>

export function reportsBorgMajor(
  borgVersions: BorgBinary[],
  major: number
): BorgBinary | undefined {
  return borgVersions.find(
    (binary) =>
      Boolean(binary) && binary.major !== undefined && String(binary.major) === String(major)
  )
}

/**
 * The installer flags that put the server's Borg 2 on an endpoint, keeping a
 * Borg 1 it reports. The same rule as `agent_borg2_reinstall_flags` in
 * app/services/repository_executor.py, which words the refusal of a job.
 */
export function borg2ReinstallFlags(borgVersions?: BorgBinary[] | null): string {
  const borgVersion = reportsBorgMajor(borgVersions ?? [], 1) ? 'both' : '2'
  return `--reinstall --borg-version ${borgVersion} --borg-source server`
}

/** The parameters of the `managedAgents.page.borg2Minimum` texts. */
export function borg2MinimumParams(
  borgVersions: BorgBinary[] | null | undefined,
  minimumVersion: string | null | undefined
): { version: string; minimum: string; flags: string } {
  // The agent runs `borg2` for Borg 2 jobs, so only that entry counts (or
  // one that names no path), as on the server (`agent_borg2_version`).
  const borg2 = (borgVersions ?? []).find(
    (binary) =>
      Boolean(binary) &&
      String(binary.major) === '2' &&
      (typeof binary.path !== 'string' ||
        !binary.path ||
        binary.path.replace(/\/+$/, '').split('/').pop() === 'borg2')
  )
  const reported = borg2?.version
  return {
    version: typeof reported === 'string' ? reported : '',
    minimum: minimumVersion ?? '',
    flags: borg2ReinstallFlags(borgVersions),
  }
}
