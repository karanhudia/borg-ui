export function normalizeBrowserPath(path?: string | null) {
  if (!path || path === '/') {
    return ''
  }
  return path.replace(/^\/+/, '').replace(/\/+$/, '')
}

export function joinBrowserPath(basePath?: string | null, childPath?: string | null) {
  const base = normalizeBrowserPath(basePath)
  const child = normalizeBrowserPath(childPath)

  if (!child) {
    return base
  }
  if (!base || child === base || child.startsWith(`${base}/`)) {
    return child
  }
  return `${base}/${child}`
}
