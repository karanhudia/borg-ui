export function normalizeBrowserPath(path?: string | null) {
  if (!path || path === '/') {
    return ''
  }
  return path.replace(/^\/+/, '').replace(/\/+$/, '')
}
