#!/usr/bin/env node

import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { resolveSnapshotOutputDir } from './snapshot-output-config.mjs'

export function buildArgosUploadArgs(frontendRoot, env = process.env) {
  return ['exec', '--', 'argos', 'upload', resolveSnapshotOutputDir(frontendRoot, env)]
}

export function uploadArgosSnapshots({
  frontendRoot = process.cwd(),
  env = process.env,
  stdio = 'inherit',
} = {}) {
  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  const child = spawn(npmCommand, buildArgosUploadArgs(frontendRoot, env), {
    cwd: frontendRoot,
    env,
    stdio,
  })

  child.on('error', (error) => {
    console.error(error)
    process.exit(1)
  })

  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal)
      return
    }

    process.exit(code ?? 1)
  })
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  uploadArgosSnapshots()
}
