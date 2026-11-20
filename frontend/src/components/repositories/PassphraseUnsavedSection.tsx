import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { repositoriesAPI } from '../../services/api'
import PassphraseUnsavedBanner from './PassphraseUnsavedBanner'
import RevealPassphraseDialog from './RevealPassphraseDialog'

interface Repo {
  id: number
  name: string
  passphrase_unsaved?: boolean
}

/** Banner plus reveal dialog for generated passphrases; `?reveal={id}` opens
 *  the dialog, as the MCP hand-off link does (spec 2026-11-14-mcp-server 5.9). */
export default function PassphraseUnsavedSection({ repositories }: { repositories: Repo[] }) {
  const { t } = useTranslation()
  const { user, proxyAuthEnabled } = useAuth()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [openId, setOpenId] = useState<number | null>(null)

  const revealParam = searchParams.get('reveal')
  useEffect(() => {
    if (revealParam === null) return
    const id = Number(revealParam)
    if (repositories.some((repo) => repo.id === id && repo.passphrase_unsaved)) setOpenId(id)
    if (repositories.length === 0) return // wait for the list before dropping the param
    const next = new URLSearchParams(searchParams)
    next.delete('reveal')
    setSearchParams(next, { replace: true })
  }, [revealParam, repositories, searchParams, setSearchParams])

  const repo = repositories.find((item) => item.id === openId)
  const reauth =
    !proxyAuthEnabled && (user?.auth_source ?? 'local') === 'local' ? 'password' : 'name'

  const downloadKeyfile = async () => {
    if (!repo) return
    try {
      const response = await repositoriesAPI.downloadKeyfile(repo.id)
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `borg_keyfile_${repo.name}`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 100)
    } catch {
      toast.error(t('repositoryInfoDialog.failedToDownloadKeyfile'))
    }
  }

  return (
    <>
      <PassphraseUnsavedBanner repositories={repositories} onReveal={setOpenId} />
      {repo && (
        <RevealPassphraseDialog
          // A new repository starts the dialog over, so one repository's
          // revealed passphrase never shows under another's name.
          key={repo.id}
          open
          repositoryName={repo.name}
          reauth={reauth}
          onReveal={async (body) => (await repositoriesAPI.revealPassphrase(repo.id, body)).data}
          onAcknowledge={async () => {
            await repositoriesAPI.acknowledgePassphrase(repo.id)
            await queryClient.invalidateQueries({ queryKey: ['repositories'] })
          }}
          onDownloadKeyfile={downloadKeyfile}
          onClose={() => setOpenId(null)}
        />
      )}
    </>
  )
}
