/** Make an archive-derived value safe to use as a mount directory name. */
export function sanitizeMountPoint(value: string): string {
  return value.replace(/[/:]/g, '_').replace(/\s+/g, '_')
}

/**
 * Default mount point for an archive.
 *
 * Borg 1 archive names are unique, so the sanitised name is enough. Borg 2
 * series archives share one name, so the archive's full start timestamp is
 * appended to keep the default distinct per archive. The raw ISO `start` (UTC as delivered
 * by the API) is used rather than a formatted local time: the result is the
 * same on every client and needs no date parsing.
 */
export function getDefaultMountPoint(
  archive: { name: string; start?: string | null },
  borgVersion?: number | null
): string {
  if (borgVersion === 2 && archive.start) {
    // Keep the full precision Borg reports (microseconds): only the zone suffix
    // goes, so even two archives created within the same second differ.
    const stamp = archive.start.replace(/(Z|[+-]\d{2}:?\d{2})$/, '')
    return sanitizeMountPoint(`${archive.name}-${stamp}`)
  }
  return sanitizeMountPoint(archive.name)
}
