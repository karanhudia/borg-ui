import type { ComponentType } from 'react'
import type { Theme } from '@mui/material'
import {
  File,
  FileArchive,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  FileAudio,
  Folder,
  KeyRound,
} from 'lucide-react'

// One mapping from a file name to the icon and colour every file list
// uses, so an image reads as an image in the archive browser, the restore
// wizard, and the details pane alike.
export type FileKind =
  | 'directory'
  | 'image'
  | 'video'
  | 'audio'
  | 'document'
  | 'sheet'
  | 'code'
  | 'archive'
  | 'text'
  | 'key'
  | 'file'

const KIND_BY_EXTENSION: Record<string, FileKind> = {
  jpg: 'image',
  jpeg: 'image',
  png: 'image',
  gif: 'image',
  webp: 'image',
  heic: 'image',
  svg: 'image',
  bmp: 'image',
  tif: 'image',
  tiff: 'image',
  raw: 'image',
  mp4: 'video',
  mov: 'video',
  mkv: 'video',
  avi: 'video',
  webm: 'video',
  mp3: 'audio',
  wav: 'audio',
  flac: 'audio',
  aac: 'audio',
  m4a: 'audio',
  ogg: 'audio',
  pdf: 'document',
  doc: 'document',
  docx: 'document',
  odt: 'document',
  rtf: 'document',
  pages: 'document',
  ppt: 'document',
  pptx: 'document',
  key: 'document',
  xls: 'sheet',
  xlsx: 'sheet',
  csv: 'sheet',
  ods: 'sheet',
  numbers: 'sheet',
  js: 'code',
  ts: 'code',
  tsx: 'code',
  jsx: 'code',
  py: 'code',
  rb: 'code',
  go: 'code',
  rs: 'code',
  java: 'code',
  c: 'code',
  h: 'code',
  cpp: 'code',
  sh: 'code',
  json: 'code',
  yaml: 'code',
  yml: 'code',
  toml: 'code',
  ini: 'code',
  xml: 'code',
  html: 'code',
  css: 'code',
  sql: 'code',
  zip: 'archive',
  tar: 'archive',
  gz: 'archive',
  tgz: 'archive',
  bz2: 'archive',
  xz: 'archive',
  '7z': 'archive',
  rar: 'archive',
  dmg: 'archive',
  iso: 'archive',
  txt: 'text',
  md: 'text',
  log: 'text',
  conf: 'text',
  cfg: 'text',
  pem: 'key',
  pub: 'key',
  gpg: 'key',
  asc: 'key',
  p12: 'key',
  pfx: 'key',
}

export function fileKindFor(name: string, type: 'file' | 'directory'): FileKind {
  if (type === 'directory') return 'directory'
  const lower = name.toLowerCase()
  if (lower.includes('keyfile') || lower.startsWith('id_')) return 'key'
  const index = lower.lastIndexOf('.')
  if (index < 0) return 'file'
  return KIND_BY_EXTENSION[lower.slice(index + 1)] ?? 'file'
}

export const FILE_KIND_ICONS: Record<FileKind, ComponentType<{ size?: number; color?: string }>> = {
  directory: Folder,
  image: FileImage,
  video: FileVideo,
  audio: FileAudio,
  document: FileText,
  sheet: FileSpreadsheet,
  code: FileCode,
  archive: FileArchive,
  text: FileText,
  key: KeyRound,
  file: File,
}

export function fileKindColor(theme: Theme, kind: FileKind): string {
  switch (kind) {
    case 'directory':
      return theme.palette.warning.main
    case 'image':
    case 'video':
    case 'audio':
      return theme.palette.secondary.main
    case 'document':
      return theme.palette.error.main
    case 'sheet':
      return theme.palette.success.main
    case 'code':
      return theme.palette.info.main
    case 'archive':
      return theme.palette.warning.dark
    case 'text':
      return theme.palette.primary.main
    case 'key':
      return theme.palette.warning.dark
    default:
      return theme.palette.text.secondary
  }
}
