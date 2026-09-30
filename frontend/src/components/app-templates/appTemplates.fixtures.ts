import type { AppDetection, AppFolderStats, AppTemplate } from '../../services/api'

// Copy of app/app_templates/immich-logo.svg (Immich's official logo).
const immichLogo =
  '<?xml version="1.0" encoding="utf-8"?>\n<!-- Generator: Adobe Illustrator 28.3.0, SVG Export Plug-In . SVG Version: 6.00 Build 0)  -->\n<svg version="1.1" id="Flower" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" x="0px" y="0px"\n\t viewBox="0 0 792 792" style="enable-background:new 0 0 792 792;" xml:space="preserve">\n<style type="text/css">\n\t.st0{fill:#FA2921;}\n\t.st1{fill:#ED79B5;}\n\t.st2{fill:#FFB400;}\n\t.st3{fill:#1E83F7;}\n\t.st4{fill:#18C249;}\n</style>\n<g id="Flower_00000077325900055813483940000000694823054982625702_">\n\t<path class="st0" d="M375.48,267.63c38.64,34.21,69.78,70.87,89.82,105.42c34.42-61.56,57.42-134.71,57.71-181.3\n\t\tc0-0.33,0-0.63,0-0.91c0-68.94-68.77-95.77-128.01-95.77s-128.01,26.83-128.01,95.77c0,0.94,0,2.2,0,3.72\n\t\tC300.01,209.24,339.15,235.47,375.48,267.63z"/>\n\t<path class="st1" d="M164.7,455.63c24.15-26.87,61.2-55.99,103.01-80.61c44.48-26.18,88.97-44.47,128.02-52.84\n\t\tc-47.91-51.76-110.37-96.24-154.6-110.91c-0.31-0.1-0.6-0.19-0.86-0.28c-65.57-21.3-112.34,35.81-130.64,92.15\n\t\tc-18.3,56.34-14.04,130.04,51.53,151.34C162.05,454.77,163.25,455.16,164.7,455.63z"/>\n\t<path class="st2" d="M681.07,302.19c-18.3-56.34-65.07-113.45-130.64-92.15c-0.9,0.29-2.1,0.68-3.54,1.15\n\t\tc-3.75,35.93-16.6,81.27-35.96,125.76c-20.59,47.32-45.84,88.27-72.51,118c69.18,13.72,145.86,12.98,190.26-1.14\n\t\tc0.31-0.1,0.6-0.2,0.86-0.28C695.11,432.22,699.37,358.52,681.07,302.19z"/>\n\t<path class="st3" d="M336.54,510.71c-11.15-50.39-14.8-98.36-10.7-138.08c-64.03,29.57-125.63,75.23-153.26,112.76\n\t\tc-0.19,0.26-0.37,0.51-0.53,0.73c-40.52,55.78-0.66,117.91,47.27,152.72c47.92,34.82,119.33,53.54,159.86-2.24\n\t\tc0.56-0.76,1.3-1.78,2.19-3.01C363.28,602.32,347.02,558.08,336.54,510.71z"/>\n\t<path class="st4" d="M617.57,482.52c-35.33,7.54-82.42,9.33-130.72,4.66c-51.37-4.96-98.11-16.32-134.63-32.5\n\t\tc8.33,70.03,32.73,142.73,59.88,180.6c0.19,0.26,0.37,0.51,0.53,0.73c40.52,55.78,111.93,37.06,159.86,2.24\n\t\tc47.92-34.82,87.79-96.95,47.27-152.72C619.2,484.77,618.46,483.75,617.57,482.52z"/>\n</g>\n</svg>\n'

// Story data mirroring app/app_templates/immich.json.
export const immichTemplate: AppTemplate = {
  id: 'immich',
  version: 1,
  name: 'Immich',
  description: "Photos, videos and Immich's own database dumps.",
  logo_svg: immichLogo,
  docs_url: 'https://docs.immich.app/administration/backup-and-restore',
  verified: { app_version: 'v3.2.4', date: '2026-09-30', restore_tested: false },
  detect: { image_prefix: 'ghcr.io/immich-app/immich-server', mount_destination: '/data' },
  root_hint: 'UPLOAD_LOCATION in your Immich .env file',
  folders: [
    {
      path: 'upload',
      label: 'Uploads',
      description:
        'Your photos and videos as uploaded. This is where Immich keeps originals unless the storage template is on.',
      role: 'data',
      stale_after_hours: null,
    },
    {
      path: 'library',
      label: 'Library',
      description: "Your photos and videos, when Immich's storage template is on.",
      role: 'data',
      stale_after_hours: null,
    },
    {
      path: 'profile',
      label: 'Profile pictures',
      description: 'Pictures users set for their accounts.',
      role: 'data',
      stale_after_hours: null,
    },
    {
      path: 'backups',
      label: 'Database dumps',
      description:
        "Immich's nightly copy of its database: albums, people, faces, descriptions and settings.",
      role: 'database',
      stale_after_hours: 26,
    },
    {
      path: 'thumbs',
      label: 'Previews',
      description: 'Thumbnails and preview images. Immich rebuilds them after a restore.',
      role: 'rebuildable',
      stale_after_hours: null,
    },
    {
      path: 'encoded-video',
      label: 'Re-encoded videos',
      description:
        'Smaller copies of your videos for streaming. Immich rebuilds them after a restore.',
      role: 'rebuildable',
      stale_after_hours: null,
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
    'After a restore with previews or re-encoded videos skipped, run the Generate Thumbnails and Transcode Videos jobs in Immich.',
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

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString()

export const immichStats: AppFolderStats[] = [
  {
    path: 'upload',
    exists: true,
    size_bytes: 412_000_000_000,
    latest_name: null,
    latest_modified_at: null,
  },
  { path: 'library', exists: false, size_bytes: null, latest_name: null, latest_modified_at: null },
  {
    path: 'profile',
    exists: true,
    size_bytes: 3_400_000,
    latest_name: null,
    latest_modified_at: null,
  },
  {
    path: 'backups',
    exists: true,
    size_bytes: 1_250_000_000,
    latest_name: 'immich-db-backup-20260930T020000.sql.gz',
    latest_modified_at: hoursAgo(9),
  },
  {
    path: 'thumbs',
    exists: true,
    size_bytes: 38_000_000_000,
    latest_name: null,
    latest_modified_at: null,
  },
  {
    path: 'encoded-video',
    exists: true,
    size_bytes: 21_000_000_000,
    latest_name: null,
    latest_modified_at: null,
  },
]
