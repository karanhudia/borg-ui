/** Split a path into its directory and its basename, so a row can print the
 *  directory as context and the basename at full contrast. */
export function splitPath(path: string): { dir: string; name: string } {
  const index = path.lastIndexOf('/')
  if (index < 0) return { dir: '', name: path }
  return { dir: path.slice(0, index + 1), name: path.slice(index + 1) }
}
