import { toast } from 'react-hot-toast'
import i18n from '../i18n'
import { BorgApiClient, type Repository } from '../services/borgApi/client'
import { translateBackendKey, type BackendDetail } from './translateBackendKey'
import { formatBytes } from './dateUtils'

/**
 * Download a single file from an archive and save it, with a live activity
 * toast (bytes transferred, or a percentage once the total size is known) and
 * proper backend-error surfacing.
 *
 * `toast` and `i18n`/`translateBackendKey` are context-free singletons, so this
 * works outside a React render stack. The agent-streamed download has no
 * Content-Length, so progress usually shows bytes; a caller-supplied `totalSize`
 * (from the archive listing) turns it into a percentage.
 */
export async function downloadArchiveFile(
  repository: Repository,
  archiveId: string,
  filePath: string,
  options?: { totalSize?: number }
): Promise<void> {
  const filename = filePath.split('/').pop() || filePath || 'download'
  // duration: Infinity so the activity toast never auto-dismisses mid-download;
  // it is resolved explicitly to success/error (which use their own duration).
  const toastId = toast.loading(i18n.t('archiveContents.downloadPreparing', { name: filename }), {
    duration: Infinity,
  })
  let lastShownMb = -1

  try {
    const response = await new BorgApiClient(repository).fetchArchiveFile(archiveId, filePath, {
      onDownloadProgress: (event) => {
        // Throttle to whole-MB changes so the toast is not updated per chunk.
        const mb = Math.floor(event.loaded / (1024 * 1024))
        if (mb === lastShownMb) return
        lastShownMb = mb

        const total = event.total || options?.totalSize
        const message = total
          ? i18n.t('archiveContents.downloadingPercent', {
              percent: Math.min(100, Math.round((event.loaded / total) * 100)),
              size: formatBytes(event.loaded),
            })
          : i18n.t('archiveContents.downloadingBytes', { size: formatBytes(event.loaded) })
        toast.loading(message, { id: toastId, duration: Infinity })
      },
    })

    const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)

    // Explicit finite duration: the loading toast set duration:Infinity, which
    // react-hot-toast keeps across the same-id update unless overridden.
    toast.success(i18n.t('archiveContents.downloadComplete', { name: filename }), {
      id: toastId,
      duration: 4000,
    })
  } catch (err: unknown) {
    let detail: BackendDetail
    const data = (err as { response?: { data?: unknown } })?.response?.data
    if (data instanceof Blob) {
      // With responseType:'blob' the error body also comes back as a Blob.
      try {
        detail = JSON.parse(await data.text())?.detail
      } catch {
        detail = undefined
      }
    } else if (data && typeof data === 'object') {
      detail = (data as { detail?: BackendDetail }).detail
    }
    toast.error(translateBackendKey(detail, 'archiveContents.failedToDownloadFile'), {
      id: toastId,
      duration: 6000,
    })
  }
}
