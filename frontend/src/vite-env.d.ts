/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_VERSION?: string
  readonly VITE_API_URL: string
  readonly VITE_ANNOUNCEMENTS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
