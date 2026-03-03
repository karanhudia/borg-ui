import i18n from '../i18n'

type BackendDetail = string | { key: string; params?: Record<string, unknown> } | null | undefined

/**
 * Translates a backend-originating detail/message value into a user-facing string.
 *
 * Handles four input shapes emitted by the backend (in order of priority):
 *   Shape 1: { key: string; params?: object }  — structured object (new backend format)
 *   Shape 2: JSON-encoded Shape 1 string        — stored error_message format
 *   Shape 3: dot-notation key string            — simple key (new backend format)
 *   Shape 4: raw English string                 — legacy backend, returned verbatim
 *
 * Call from mutation onError/onSuccess handlers via `i18n.t()` directly —
 * NOT via useTranslation() which requires a React component render stack.
 */
export function translateBackendKey(
  detail: BackendDetail,
  fallbackKey = 'common.errors.unexpectedError'
): string {
  if (detail === null || detail === undefined) {
    return String(i18n.t(fallbackKey))
  }

  // Shape 1: { key, params } object — new backend structured format
  if (typeof detail === 'object' && typeof detail.key === 'string') {
    return String(i18n.t(detail.key, detail.params ?? {}))
  }

  // Shape 2: JSON-encoded { key, params } string — stored error_message format
  if (typeof detail === 'string' && detail.startsWith('{')) {
    try {
      const parsed = JSON.parse(detail)
      if (parsed !== null && typeof parsed === 'object' && typeof parsed.key === 'string') {
        return String(i18n.t(parsed.key, parsed.params ?? {}))
      }
    } catch {
      // Not valid JSON — fall through to string shapes
    }
  }

  // Shape 3: dot-notation key string — new backend simple key format
  if (typeof detail === 'string' && /^[\w]+\.[\w.]+$/.test(detail)) {
    return String(i18n.t(detail))
  }

  // Shape 4: raw English string — legacy backend, return as-is
  if (typeof detail === 'string') {
    return detail
  }

  return String(i18n.t(fallbackKey))
}
