import { toast } from 'react-hot-toast'
import { BorgApiClient, type Repository } from '../services/borgApi/client'
import { translateBackendKey, type BackendDetail } from './translateBackendKey'

/**
 * Download a single file from an archive and save it, surfacing backend errors
 * as a toast instead of navigating the browser to a raw JSON error page.
 *
 * Follows the established BorgUI download convention (see
 * RepositoryInfoDialog.handleDownloadKeyfile): fetch as a Blob via XHR, and on
 * failure read the error Blob body, parse its `detail`, and localise it via
 * `translateBackendKey`. `toast` and `translateBackendKey` are context-free
 * singletons, so this works outside a React render stack.
 */
export async function downloadArchiveFile(
  repository: Repository,
  archiveId: string,
  filePath: string
): Promise<void> {
  try {
    const response = await new BorgApiClient(repository).fetchArchiveFile(archiveId, filePath)
    const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filePath.split('/').pop() || filePath || 'download'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
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
    toast.error(translateBackendKey(detail, 'archiveContents.failedToDownloadFile'))
  }
}
