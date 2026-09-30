import type { AppDetection, AppTemplate } from '../../services/api'

// Story data mirroring app/app_templates/immich.json.
export const immichTemplate: AppTemplate = {
  id: 'immich',
  version: 1,
  name: 'Immich',
  description: "Photos, videos and Immich's own database dumps.",
  docs_url: 'https://docs.immich.app/administration/backup-and-restore',
  verified: { app_version: 'v3.2.4', date: '2026-09-30', restore_tested: false },
  detect: { image_prefix: 'ghcr.io/immich-app/immich-server', mount_destination: '/data' },
  root_hint: 'UPLOAD_LOCATION in your Immich .env file',
  excludes: [
    { path: 'thumbs', default: true, label: 'Skip previews (Immich rebuilds them)' },
    {
      path: 'encoded-video',
      default: true,
      label: 'Skip re-encoded videos (Immich rebuilds them)',
    },
  ],
  pre_backup_script: {
    name: 'Check Immich database dump',
    description: 'Stop the backup if Immich has not written a database dump in the last 26 hours.',
    content: 'APP_ROOT=__APP_ROOT__\n',
    timeout: 60,
  },
  schedule_cron: '0 3 * * *',
  notes: [
    "Keep Administration > Settings > Backup turned on in Immich. This backup relies on Immich's own daily database dumps in the backups folder.",
    'After restoring with previews skipped, run the Generate Thumbnails and Transcode Videos jobs for all assets.',
  ],
}

export const immichFound: AppDetection = {
  template_id: 'immich',
  container_name: 'immich_server',
  state: 'running',
  path: '/local/srv/immich',
  host_path: '/srv/immich',
  readable: true,
}
