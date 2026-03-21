/**
 * Base path for sub-directory reverse proxy deployment (e.g., /borg-ui).
 * Injected at runtime by the backend when BASE_PATH env var is set.
 */
const _basePath = (window as unknown as { __BASE_PATH__?: string }).__BASE_PATH__ || ''
export const BASE_PATH = _basePath === '/' ? '' : _basePath
